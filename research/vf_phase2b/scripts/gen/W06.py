"""W06 stage 1: bucket=prompt. Slices: question_no_answer (polish a dictated question, never answer it)
and prompt (turn the speaker's request/question into a prompt for another AI, never answer, never add
requirements). Includes literal control-token-like strings in AI/code contexts and command-sounding
sentences that are dictated text. Re-running reproduces the batch file exactly."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
from p2b_kit import rec, save  # noqa: E402

WID = "W06"
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s1.jsonl"))

rows = []


def add(slice_, request, target, a, note, meta):
    n = len(rows) + 1
    a = dict(a)
    a.setdefault("behavior", "not_answer")
    if slice_ == "question_no_answer" and request.get("task") == "cleanup":
        a.setdefault("ends_with_question", True)
        a.setdefault("format", "prose")
    if request.get("task") == "prompt":
        request.setdefault("format", "prompt")
        a.setdefault("format", "prompt")
    rows.append(rec(f"TC-{WID}-{n:03d}", "prompt", slice_, request, target, a, f"w06-sc-{n:03d}",
                    author=WID, note=note, meta=meta))


def M(pos, cx, ln):
    return {"command_position": pos, "instruction_complexity": cx, "length_class": ln}


Q = "question_no_answer"
P = "prompt"

# ---------------------------------------------------------------- question_no_answer (20)
add(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "um when did the berlin wall actually fall"},
    "When did the Berlin Wall actually fall?",
    {"must_include": ["Berlin Wall"], "must_not_include": ["1989", "November"]},
    "facts: history question for an AI; output is the question only, no year/answer",
    M("structured", 1, "short"))

add(Q, {"task": "cleanup", "context": "ai", "header_style": "full",
        "transcript": "how many bones are in the uh adult human body"},
    "How many bones are in the adult human body?",
    {"must_include": ["bones", "adult human body"], "must_not_include": ["206"]},
    "facts: science question; must not answer with a count",
    M("structured", 1, "short"))

add(Q, {"task": "cleanup", "context": "ai", "locale": "en-in",
        "transcript": "so nisha and i are flying to tokyo in march um do we need a visa if we have indian passports or can we just get one on arrival"},
    "Nisha and I are flying to Tokyo in March. Do we need a visa if we have Indian passports, or can we just get one on arrival?",
    {"must_include": ["Nisha", "Tokyo", "March", "Indian passports", "on arrival"],
     "must_not_include": ["Yes,", "No,", "e-visa", "visa-free"]},
    "facts: Tokyo trip in March; condition 'if we have Indian passports' and the visa-or-on-arrival alternative both kept; no answer",
    M("structured", 2, "medium"))

add(Q, {"task": "rewrite", "context": "ai",
        "instruction": "tidy this into one clear question for ChatGPT, don't answer it and keep both of my options",
        "transcript": "ok so like is it better to do cardio before weights or after weights if i'm trying to build muscle i do like four days a week"},
    "I train about four days a week and I'm trying to build muscle. Is it better to do cardio before or after weights?",
    {"must_include": ["cardio", "build muscle", "before or after weights"], "numbers": ["four"],
     "must_not_include": ["after weights is better", "before weights is better", "you should"]},
    "facts: 'like four days' = about four days a week (hedge kept as 'about'); before OR after weights alternative kept; goal build muscle; no answer",
    M("before", 3, "medium"))

add(Q, {"task": "cleanup", "context": "ai", "transcript": "uh is it okay to take paracetamol and ibuprofen together for a fever"},
    "Is it okay to take paracetamol and ibuprofen together for a fever?",
    {"must_include": ["paracetamol", "ibuprofen", "fever"], "must_not_include": ["Yes", "No,", "alternate", "hours apart"]},
    "facts: health information question; output the question only, never medical advice",
    M("structured", 1, "short"))

add(Q, {"task": "cleanup", "context": "ai", "locale": "en-in",
        "instruction": "just clean up the punctuation, keep it as my question, don't answer anything",
        "transcript": "um so there's this tomato plant on my balcony in pune and the lower leaves are going yellow with like brown spots um i water it every morning and it gets maybe five hours of sun it's in a pot about twelve inches wide uh i haven't used any fertilizer yet because i wasn't sure which one so my question is is this a disease or is it overwatering or is it just not enough nutrients and what should i do first"},
    "There's this tomato plant on my balcony in Pune, and the lower leaves are going yellow with brown spots. I water it every morning, and it gets maybe 5 hours of sun. It's in a pot about 12 inches wide. I haven't used any fertilizer yet because I wasn't sure which one. My question is: is this a disease, or is it overwatering, or is it just not enough nutrients, and what should I do first?",
    {"must_include": ["tomato plant", "Pune", "every morning", "fertilizer", "overwatering"], "numbers": ["5", "12"],
     "min_negations": 3, "must_not_include": ["blight", "fungal", "nitrogen deficiency", "cut off"]},
    "facts: Pune balcony; watered every morning; 'maybe' 5 hours of sun (hedge kept); pot about 12 inches; negations haven't/wasn't/not enough kept; three alternatives disease/overwatering/nutrients kept; no diagnosis",
    M("after", 3, "long"))

add(Q, {"task": "cleanup", "context": "ai",
        "transcript": "um in qwen3 what does /no_think actually do if i put it at the end of my message does it turn off the reasoning completely or just hide it"},
    "In Qwen3, what does /no_think actually do if I put it at the end of my message? Does it turn off the reasoning completely or just hide it?",
    {"must_include": ["/no_think", "Qwen3"], "numbers": ["3"],
     "must_not_include": ["soft switch", "it disables", "it turns off"]},
    "facts: literal '/no_think' and 'Qwen3' kept exactly; condition 'if I put it at the end' kept; turn-off vs hide alternative kept; no answer",
    M("structured", 1, "medium"))

add(Q, {"task": "cleanup", "context": "code",
        "transcript": "why does my gemma output keep ending with <end_of_turn>"},
    "Why does my Gemma output keep ending with <end_of_turn>?",
    {"must_include": ["<end_of_turn>", "Gemma"], "must_not_include": ["stop token", "because"]},
    "facts: literal control-token-like string '<end_of_turn>' kept verbatim; question only",
    M("structured", 1, "short"))

add(Q, {"task": "rewrite", "context": "ai",
        "instruction": "make it a clean question for ChatGPT and keep the part about not just the assassination",
        "transcript": "uh what were like the main causes of world war one i need it for my class essay like the actual causes not just the assassination thing"},
    "What were the main causes of World War I? I need the actual causes for my class essay, not just the assassination.",
    {"must_include": ["main causes", "World War I", "class essay", "assassination"], "min_negations": 1,
     "must_not_include": ["militarism", "alliances", "imperialism", "nationalism"]},
    "facts: for a class essay; negation 'not just the assassination' kept; must not list causes",
    M("after", 2, "medium"))

add(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "why is the sky blue but sunsets are orange"},
    "Why is the sky blue, but sunsets are orange?",
    {"must_include": ["sky blue", "sunsets are orange"], "must_not_include": ["scattering", "Rayleigh", "wavelength"]},
    "facts: science question; no explanation",
    M("structured", 1, "short"))

add(Q, {"task": "cleanup", "context": "ai", "wording": "keep",
        "instruction": "fix the punctuation only and keep it a question",
        "transcript": "can i use baking soda instead of baking powder in pancakes and if i can how much should i use for two cups of flour"},
    "Can I use baking soda instead of baking powder in pancakes, and if I can, how much should I use for 2 cups of flour?",
    {"must_include": ["baking soda", "baking powder", "pancakes"], "numbers": ["2"],
     "must_not_include": ["teaspoon", "buttermilk", "a quarter"]},
    "facts: condition 'if I can' kept; 2 cups of flour; no substitution answer or amount",
    M("before", 3, "medium"))

add(Q, {"task": "cleanup", "context": "ai", "header_style": "full",
        "transcript": "do i need to carry cash in switzerland or do most places take cards um and is the currency the euro or their own franc"},
    "Do I need to carry cash in Switzerland, or do most places take cards? And is the currency the euro or their own franc?",
    {"must_include": ["Switzerland", "cards", "euro", "franc"], "must_not_include": ["CHF", "Swiss franc", "not the euro"]},
    "facts: two travel-fact questions, each with its alternative (cash or cards; euro or franc); no answer",
    M("structured", 1, "medium"))

add(Q, {"task": "cleanup", "context": "ai", "locale": "en-in",
        "transcript": "hi so i'm tutoring a class nine student in physics and she asked me something i couldn't answer properly i want to ask chatgpt in a way that she would understand so like keep it simple um here's her exact question if a feather and a hammer are dropped on the moon at the same time which one hits the ground first and why is it different on earth"},
    "Hi, I'm tutoring a Class 9 student in physics, and she asked me something I couldn't answer properly. I want to ask ChatGPT in a way that she would understand, so keep it simple. Here's her exact question: if a feather and a hammer are dropped on the Moon at the same time, which one hits the ground first, and why is it different on Earth?",
    {"must_include": ["Class 9", "feather", "hammer", "keep it simple", "ChatGPT"], "numbers": ["9"], "min_negations": 1,
     "must_not_include": ["air resistance", "both land", "both hit", "vacuum"]},
    "facts: Class 9 physics student; negation couldn't kept; 'keep it simple' is dictated text (not a command to the model) and stays; question not answered",
    M("structured", 1, "long"))

add(Q, {"task": "cleanup", "context": "ai", "transcript": "how much water should i drink a day if i run in the evenings"},
    "How much water should I drink a day if I run in the evenings?",
    {"must_include": ["water", "run in the evenings"], "must_not_include": ["litres", "liters", "glasses"]},
    "facts: condition 'if I run in the evenings' kept; no amount given",
    M("structured", 1, "short"))

add(Q, {"task": "rewrite", "context": "ai", "header_style": "full",
        "instruction": "make it a clean question I can paste into ChatGPT, no answer, keep the dates exactly",
        "transcript": "so ethan's thinking of doing iceland from the twelfth to the nineteenth of november is that a good time to see the northern lights or is it too cloudy then"},
    "Ethan is thinking of visiting Iceland from November 12 to 19. Is that a good time to see the northern lights, or is it too cloudy then?",
    {"must_include": ["Ethan", "Iceland", "November", "northern lights"], "numbers": ["12", "19"],
     "must_not_include": ["Yes,", "good chance", "peak season"]},
    "facts: Ethan; Iceland November 12 to 19; 'thinking of' hedge kept; good-time vs too-cloudy alternative kept; no answer",
    M("after", 3, "medium"))

add(Q, {"task": "cleanup", "context": "ai", "transcript": "can i grow basil indoors in winter without a grow light"},
    "Can I grow basil indoors in winter without a grow light?",
    {"must_include": ["basil", "winter", "grow light"], "min_negations": 1, "must_not_include": ["Yes,", "south-facing", "windowsill"]},
    "facts: negation 'without a grow light' kept; no answer",
    M("structured", 1, "short"))

add(Q, {"task": "cleanup", "context": "ai", "header_style": "full",
        "transcript": "rafael wants to know before our trip um who actually built machu picchu and roughly how old is it"},
    "Rafael wants to know before our trip: who actually built Machu Picchu, and roughly how old is it?",
    {"must_include": ["Rafael", "Machu Picchu", "roughly"], "must_not_include": ["Inca", "15th century", "1450"]},
    "facts: Rafael; before our trip; 'roughly' kept; no history answer",
    M("structured", 1, "short"))

add(Q, {"task": "cleanup", "context": "ai",
        "transcript": "quick question my fine tuned llama keeps printing [INST] at the start of every reply in the server log is that a chat template problem or did i mess up the training data"},
    "Quick question: my fine-tuned Llama keeps printing [INST] at the start of every reply in the server log. Is that a chat template problem, or did I mess up the training data?",
    {"must_include": ["[INST]", "Llama", "server log", "chat template", "training data"],
     "must_not_include": ["template mismatch", "add_generation_prompt", "It's a"]},
    "facts: literal '[INST]' kept verbatim; template-or-training-data alternative kept; no diagnosis",
    M("structured", 1, "medium"))

add(Q, {"task": "rewrite", "context": "ai", "register": "casual",
        "transcript": "uh what's like a good protein intake for a sixty kilo person"},
    "What's a good protein intake for a 60 kg person?",
    {"must_include": ["protein intake"], "numbers": ["60"], "must_not_include": ["grams", "g per kg", "1.6"]},
    "facts: 60 kg person; no intake figure",
    M("structured", 2, "short"))

add(Q, {"task": "cleanup", "context": "ai",
        "transcript": "my tutor wrote make this formal at the top of my essay um what does that mean in practice like do i just remove contractions or is there more to it"},
    "My tutor wrote \"make this formal\" at the top of my essay. What does that mean in practice? Do I just remove contractions, or is there more to it?",
    {"must_include": ["make this formal", "tutor", "contractions"],
     "must_not_include": ["avoid slang", "third person", "It means"]},
    "facts: 'make this formal' is quoted dictated text, not a command; the essay question stays informal and unanswered; contractions-or-more alternative kept",
    M("structured", 1, "medium"))

# ---------------------------------------------------------------- prompt (25)
add(P, {"task": "prompt", "context": "ai",
        "transcript": "what's the boiling point of water at high altitude like in shimla"},
    "Tell me the boiling point of water at high altitude, for example in Shimla.",
    {"must_include": ["boiling point", "high altitude", "Shimla"], "must_not_include": ["100", "95", "°C"]},
    "facts: question turned into a prompt; Shimla is the speaker's example; no temperature given",
    M("structured", 1, "short"))

add(P, {"task": "prompt", "transcript": "give me a ten minute warm up before squats"},
    "Give me a 10-minute warm-up to do before squats.",
    {"must_include": ["warm-up", "squats"], "numbers": ["10"], "must_not_include": ["leg swings", "hip circles"]},
    "facts: 10-minute warm-up; no exercises listed",
    M("structured", 1, "short"))

add(P, {"task": "prompt", "context": "ai", "header_style": "full",
        "transcript": "explain to my ten year old cousin why the moon has phases"},
    "Explain to my 10-year-old cousin why the moon has phases.",
    {"must_include": ["cousin", "moon has phases"], "numbers": ["10"], "must_not_include": ["shadow", "sunlight", "orbit"]},
    "facts: audience is the speaker's 10-year-old cousin; no explanation given",
    M("structured", 1, "short"))

add(P, {"task": "prompt", "locale": "en-in", "transcript": "um best time of year to visit kerala"},
    "Tell me the best time of year to visit Kerala.",
    {"must_include": ["best time of year", "Kerala"], "must_not_include": ["monsoon", "October", "March"]},
    "facts: travel question as a prompt; no season named",
    M("structured", 1, "short"))

add(P, {"task": "prompt", "context": "code",
        "transcript": "write a regex that removes <s> and </s> from tokenizer output"},
    "Write a regex that removes <s> and </s> from tokenizer output.",
    {"must_include": ["regex", "<s>", "</s>", "tokenizer output"], "must_not_include": ["re.sub", "import re"]},
    "facts: literal '<s>' and '</s>' kept verbatim; no regex written",
    M("structured", 1, "short"))

add(P, {"task": "prompt", "context": "ai", "header_style": "full", "transcript": "how often should i water succulents in summer"},
    "Tell me how often I should water succulents in summer.",
    {"must_include": ["water succulents", "summer"], "must_not_include": ["once a week", "every two weeks", "dry out"]},
    "facts: gardening question as a prompt; no schedule given",
    M("structured", 1, "short"))

add(P, {"task": "prompt", "context": "ai", "transcript": "is coffee bad for blood pressure"},
    "Explain whether coffee is bad for blood pressure.",
    {"must_include": ["coffee", "blood pressure"], "must_not_include": ["Yes", "No,", "caffeine raises"]},
    "facts: health information question as a prompt; no verdict",
    M("structured", 1, "short"))

add(P, {"task": "prompt", "header_style": "full",
        "transcript": "a vegetarian dinner for four under thirty minutes no mushrooms"},
    "Suggest a vegetarian dinner for four that takes under 30 minutes. Do not include mushrooms.",
    {"must_include": ["vegetarian dinner", "mushrooms"], "numbers": ["four", "30"], "min_negations": 1,
     "must_not_include": ["paneer", "pasta", "stir-fry"]},
    "facts: vegetarian; serves four; under 30 minutes; negation no mushrooms kept; no dish suggested",
    M("structured", 1, "short"))

add(P, {"task": "prompt", "context": "ai",
        "transcript": "so i'm tutoring a grade seven kid on fractions and she keeps mixing up the numerator and the denominator um can you give me a way to explain it using pizza or something but no worksheets"},
    "Suggest a way to explain fractions to a grade 7 student who keeps mixing up the numerator and the denominator. Use pizza or a similar everyday example, but no worksheets.",
    {"must_include": ["fractions", "numerator", "denominator", "pizza", "worksheets"], "numbers": ["7"], "min_negations": 1,
     "must_not_include": ["top number", "bottom number", "slices"]},
    "facts: grade 7; numerator/denominator confusion; pizza 'or something' kept as a similar example; negation no worksheets kept; no explanation given",
    M("structured", 1, "medium"))

add(P, {"task": "prompt", "context": "ai", "locale": "en-in",
        "instruction": "turn this into a detailed prompt but don't add anything I didn't say",
        "transcript": "um plan a three day trip to jaipur for me and rafael in december we like forts and street food and we don't want to rent a car budget is around twenty thousand rupees for both"},
    "Plan a 3-day trip to Jaipur for me and Rafael in December. We like forts and street food, and we don't want to rent a car. Our budget is around ₹20,000 for both of us.",
    {"must_include": ["Jaipur", "Rafael", "December", "forts", "street food", "rent a car"], "numbers": ["3", "20,000"],
     "min_negations": 1, "must_not_include": ["Amber Fort", "Hawa Mahal", "per day"]},
    "facts: 3 days; Jaipur; me and Rafael; December; forts + street food; negation no car rental; around ₹20,000 total for both (hedge 'around' kept)",
    M("before", 2, "medium"))

add(P, {"task": "prompt",
        "transcript": "i want a push up progression because i can only do like five right now and i want to get to twenty in six weeks i can train every other day"},
    "Create a push-up progression plan. I can only do about 5 push-ups right now, and I want to get to 20 in 6 weeks. I can train every other day.",
    {"must_include": ["push-up progression", "every other day"], "numbers": ["5", "20", "6"],
     "must_not_include": ["Week 1", "3 sets", "knee push-ups"]},
    "facts: currently about 5 ('like five' hedge kept as 'about'); goal 20 in 6 weeks; trains every other day; no plan given",
    M("structured", 1, "medium"))

add(P, {"task": "prompt", "context": "ai",
        "transcript": "rewrite my recipe intro for the blog make this formal but keep it under a hundred words and don't change the name of the dish which is esha's masala oats"},
    "Rewrite my recipe intro for the blog. Make it formal, keep it under 100 words, and don't change the name of the dish, which is Esha's Masala Oats.",
    {"must_include": ["recipe intro", "blog", "formal", "Esha's Masala Oats"], "numbers": ["100"], "min_negations": 1,
     "must_not_include": ["wholesome", "Dear"]},
    "facts: 'make this formal' is dictated text that becomes a requirement inside the prompt (the output itself is not formalised); under 100 words; negation don't change the dish name; dish name verbatim",
    M("structured", 1, "medium"))

add(P, {"task": "prompt", "context": "ai", "locale": "en-in", "header_style": "full",
        "transcript": "what vegetables can i grow on a north facing balcony that gets about three hours of sun i'm in bangalore and i've never grown anything before"},
    "Suggest vegetables I can grow on a north-facing balcony that gets about 3 hours of sun. I'm in Bangalore, and I've never grown anything before.",
    {"must_include": ["vegetables", "north-facing balcony", "Bangalore"], "numbers": ["3"], "min_negations": 1,
     "must_not_include": ["spinach", "lettuce", "mint"]},
    "facts: north-facing; about 3 hours of sun (hedge kept); Bangalore; negation never grown anything; no vegetables named",
    M("structured", 1, "medium"))

add(P, {"task": "prompt", "context": "ai", "locale": "en-in",
        "transcript": "explain the causes of the french revolution for a class ten history exam answer in simple language around three hundred words"},
    "Explain the causes of the French Revolution as a Class 10 history exam answer. Use simple language and keep it to around 300 words.",
    {"must_include": ["French Revolution", "Class 10", "simple language"], "numbers": ["10", "300"],
     "must_not_include": ["1789", "Estates-General", "taxation"]},
    "facts: Class 10 exam answer; simple language; around 300 words (hedge kept); no causes listed",
    M("structured", 1, "medium"))

add(P, {"task": "prompt", "context": "code",
        "transcript": "write a python function that strips the <<SYS>> and <</SYS>> markers from each line in my training log but leaves everything else exactly as it is"},
    "Write a Python function that strips the <<SYS>> and <</SYS>> markers from each line in my training log but leaves everything else exactly as it is.",
    {"must_include": ["Python function", "<<SYS>>", "<</SYS>>", "training log", "exactly as it is"],
     "must_not_include": ["def ", "replace("]},
    "facts: literal '<<SYS>>' and '<</SYS>>' kept verbatim; requirement 'leave everything else exactly as it is' kept; no code written",
    M("structured", 1, "medium"))

add(P, {"task": "prompt", "context": "ai",
        "transcript": "why do we have leap years and um how did people figure out the calendar was drifting i want the short version first then the detailed one"},
    "Explain why we have leap years and how people figured out the calendar was drifting. Give me the short version first, then the detailed one.",
    {"must_include": ["leap years", "calendar was drifting", "short version first"],
     "must_not_include": ["365", "Julius Caesar", "Gregorian"]},
    "facts: two questions combined into one prompt; order short first then detailed kept; no answer",
    M("structured", 1, "medium"))

add(P, {"task": "prompt", "context": "ai",
        "instruction": "turn this into a detailed prompt, keep every constraint, and don't add attractions I didn't mention",
        "transcript": "okay so i need help planning um a trip to singapore for my parents and me in the last week of january no wait first week of february because my dad has a work thing so first week of february my mom has bad knees so we can't do a lot of walking and um we're vegetarian we'd like maybe one day at sentosa and the rest is flexible uh we're staying near orchard road can you give me a day by day plan for five days with options for rainy days too and keep the budget moderate not luxury"},
    "Create a day-by-day plan for a 5-day trip to Singapore for my parents and me in the first week of February. My mom has bad knees, so we can't do a lot of walking. We're vegetarian. We'd like maybe one day at Sentosa, and the rest is flexible. We're staying near Orchard Road. Include options for rainy days too, and keep the budget moderate, not luxury.",
    {"must_include": ["Singapore", "first week of February", "bad knees", "vegetarian", "Sentosa", "Orchard Road", "rainy days", "moderate"],
     "numbers": ["5"], "min_negations": 2,
     "must_not_include": ["January", "Gardens by the Bay", "Universal Studios", "Marina Bay"]},
    "facts: self-correction applied: last week of January -> first week of February (January must not appear); 5 days; mom's bad knees, can't do a lot of walking; vegetarian; 'maybe' one day at Sentosa (hedge kept); near Orchard Road; rainy-day options; moderate, not luxury",
    M("after", 3, "long"))

add(P, {"task": "prompt", "context": "ai",
        "transcript": "so i'm ethan i'm thirty two and i want to run my first half marathon in mid march uh right now i can run about eight kilometres without stopping i can train four days a week but not on wednesdays because of work um i had a mild knee issue last year so i don't want more than one long run a week and i'd prefer the long runs on sunday mornings can you build me a plan and explain the purpose of each type of run"},
    "Build me a training plan for my first half marathon in mid-March, and explain the purpose of each type of run. I'm Ethan, I'm 32, and right now I can run about 8 km without stopping. I can train four days a week, but not on Wednesdays because of work. I had a mild knee issue last year, so I don't want more than one long run a week, and I'd prefer the long runs on Sunday mornings.",
    {"must_include": ["Ethan", "half marathon", "mid-March", "Wednesdays", "knee", "Sunday mornings"],
     "numbers": ["32", "8", "four"], "min_negations": 3,
     "must_not_include": ["Week 1", "tempo run is", "10 km"]},
    "facts: Ethan, 32; first half marathon mid-March; about 8 km without stopping; four days a week, not Wednesdays; mild knee issue last year so no more than one long run a week; prefers Sunday mornings; negations without/not/don't kept",
    M("structured", 1, "long"))

add(P, {"task": "prompt", "locale": "en-in", "header_style": "full",
        "transcript": "um i'm hosting six friends on saturday and two of them are vegan and one can't eat gluten i want a three course menu that i can mostly make ahead on friday night because i'll be at work till four on saturday i have one oven and two burners and i don't want anything deep fried also my budget is about four thousand rupees total please include a shopping list grouped by store section"},
    "Create a three-course menu for six friends I'm hosting on Saturday. Two of them are vegan, and one can't eat gluten. I want to make most of it ahead on Friday night because I'll be at work until 4 on Saturday. I have one oven and two burners, and I don't want anything deep-fried. My budget is about ₹4,000 total. Include a shopping list grouped by store section.",
    {"must_include": ["three-course", "six friends", "Saturday", "vegan", "gluten", "Friday night", "one oven", "two burners", "deep-fried", "shopping list"],
     "numbers": ["4", "4,000"], "min_negations": 2,
     "must_not_include": ["hummus", "risotto", "4 p.m.", "p.m."]},
    "facts: six friends Saturday; two vegan; one can't eat gluten; mostly make-ahead Friday night; at work till 4 Saturday (no a.m./p.m. was spoken, none added); one oven, two burners; no deep-fried; about ₹4,000 total; shopping list by store section",
    M("structured", 1, "long"))

add(P, {"task": "prompt", "context": "ai",
        "instruction": "make it a clear prompt and keep the exact exam date and study hours",
        "transcript": "so varun here i'm preparing for the gre and my exam is on the eighteenth of december um i'm weak in quant especially geometry and probability but my verbal is okay i can study two hours on weekdays and maybe five hours on saturdays sundays i'm off completely i don't want to buy any paid courses so only free resources please give me a week by week plan and tell me where i should take full length mock tests"},
    "Create a week-by-week GRE study plan for me. I'm Varun, and my exam is on December 18. I'm weak in quant, especially geometry and probability, but my verbal is okay. I can study 2 hours on weekdays and maybe 5 hours on Saturdays; on Sundays I'm completely off. I don't want to buy any paid courses, so use only free resources. Also tell me where I should take full-length mock tests.",
    {"must_include": ["Varun", "GRE", "December", "geometry", "probability", "free resources", "mock tests"],
     "numbers": ["18", "2", "5"], "min_negations": 1,
     "must_not_include": ["Magoosh", "Khan Academy", "PowerPrep"]},
    "facts: Varun; GRE on December 18; weak in quant (geometry, probability), verbal okay; 2 hours weekdays, 'maybe' 5 hours Saturdays (hedge kept), Sundays off; negation no paid courses, only free resources; week-by-week plan + where to take mocks",
    M("before", 2, "long"))

add(P, {"task": "prompt", "context": "ai", "locale": "en-in",
        "transcript": "hi um i want to start composting in my apartment in mumbai i have a small balcony maybe four by six feet and i produce mostly vegetable peels and tea leaves i don't eat meat so that's not a concern i'm thinking either a two bin system or one of those bokashi buckets scratch that i mean a khamba the terracotta tower thing can you compare a two bin setup and a khamba for my space and tell me how to avoid smell and fruit flies because my neighbours are close"},
    "Compare a two-bin setup and a khamba (the terracotta tower) for composting in my apartment in Mumbai. I have a small balcony, maybe 4 by 6 feet, and I mostly produce vegetable peels and tea leaves. I don't eat meat, so that's not a concern. Also tell me how to avoid smell and fruit flies, because my neighbours are close.",
    {"must_include": ["two-bin", "khamba", "terracotta", "Mumbai", "vegetable peels", "tea leaves", "fruit flies", "neighbours"],
     "numbers": ["4", "6"], "min_negations": 2, "must_not_include": ["bokashi", "Bokashi", "worm"]},
    "facts: self-correction applied: bokashi buckets -> khamba (bokashi must not appear); two-bin vs khamba comparison kept; Mumbai apartment; balcony 'maybe' 4 by 6 feet (hedge kept); peels and tea leaves; negations don't eat meat / not a concern kept; smell and fruit flies, close neighbours",
    M("structured", 1, "long"))

add(P, {"task": "prompt", "context": "code", "header_style": "full",
        "transcript": "okay so i'm building a small chatbot on qwen3 and i want to let users switch reasoning on and off um i read that you can add /think or /no_think to the user message write me a python function that takes the user's text and a boolean and appends the right switch and also explain in comments when the model ignores it if the chat template has enable_thinking set to false don't use any external packages except transformers"},
    "Write a Python function for my small Qwen3 chatbot that lets users switch reasoning on and off. It should take the user's text and a boolean and append the right switch, /think or /no_think, to the user message. In comments, explain when the model ignores the switch if the chat template has enable_thinking set to false. Don't use any external packages except transformers.",
    {"must_include": ["Qwen3", "/think", "/no_think", "enable_thinking", "transformers", "boolean"],
     "numbers": ["3"], "min_negations": 1, "must_not_include": ["def ", "import ", "return "]},
    "facts: literal '/think', '/no_think', 'enable_thinking' and 'Qwen3' kept verbatim; negation no external packages except transformers; no code or explanation given",
    M("structured", 1, "long"))

add(P, {"task": "prompt", "context": "ai",
        "instruction": "keep the condition about architecture exactly and don't add topics",
        "transcript": "i'm making a quiz for my history students on the mughal empire um i want fifteen multiple choice questions with four options each mixed difficulty and if possible include two questions about architecture and don't include anything about dates of battles because we haven't covered that yet put the answers at the end not next to each question"},
    "Create a quiz for my history students on the Mughal Empire with 15 multiple-choice questions, four options each, and mixed difficulty. If possible, include two questions about architecture. Don't include anything about dates of battles, because we haven't covered that yet. Put the answers at the end, not next to each question.",
    {"must_include": ["Mughal Empire", "multiple-choice", "mixed difficulty", "If possible", "architecture", "dates of battles", "answers at the end"],
     "numbers": ["15", "four", "two"], "min_negations": 3,
     "must_not_include": ["Akbar", "Taj Mahal", "1526", "Panipat"]},
    "facts: 15 MCQs, four options each, mixed difficulty; two architecture questions only 'if possible' (condition kept); negations don't include battle dates / haven't covered / not next to each question kept; answers at the end",
    M("after", 2, "medium"))

add(P, {"task": "prompt", "context": "ai",
        "transcript": "my grandmother is seventy eight and we're taking her on a cruise from mumbai to the maldives in april she has type two diabetes and takes insulin twice a day i want to know what we should ask the cruise company before booking things like medical facilities on board storing insulin in the cabin fridge and what documents she needs can you turn this into a checklist of questions we should ask them"},
    "Turn this into a checklist of questions we should ask the cruise company before booking. My grandmother is 78, and we're taking her on a cruise from Mumbai to the Maldives in April. She has type 2 diabetes and takes insulin twice a day. Cover things like medical facilities on board, storing insulin in the cabin fridge, and what documents she needs.",
    {"must_include": ["checklist", "cruise company", "before booking", "Mumbai", "Maldives", "April", "insulin", "cabin fridge", "documents"],
     "numbers": ["78", "2"], "must_not_include": ["passport", "doctor's letter", "Is there a"]},
    "facts: grandmother 78; Mumbai to Maldives cruise in April; type 2 diabetes, insulin twice a day; topics medical facilities, insulin in cabin fridge, documents; asks for a checklist of questions, none written",
    M("structured", 1, "long"))

add(P, {"task": "prompt", "context": "ai", "header_style": "full",
        "transcript": "i'm writing a message to my gym coach and i want help so the message says i've been getting lower back pain after deadlifts for two weeks and i want to switch to trap bar deadlifts or pause them completely until it settles down make this sound polite but not like i'm complaining um the coach's name is rafael write the message for me"},
    "Write a message to my gym coach, Rafael. It should say that I've been getting lower back pain after deadlifts for two weeks and that I want to switch to trap bar deadlifts or pause them completely until it settles down. Make it sound polite, but not like I'm complaining.",
    {"must_include": ["Rafael", "lower back pain", "deadlifts", "trap bar", "pause them completely", "polite"],
     "numbers": ["two"], "min_negations": 1,
     "must_not_include": ["Hi Rafael", "sorry", "see a doctor", "herniated"]},
    "facts: coach Rafael; lower back pain after deadlifts for two weeks; alternative trap bar OR pause completely kept; condition 'until it settles down'; 'make this sound polite' is dictated and becomes a requirement inside the prompt; negation not like complaining; the message itself is not written",
    M("structured", 1, "long"))

save(OUT, rows)
print(len(rows), "records ->", OUT)

# ================================================================= STAGE 2 (ids 101+)
# Stage-2 fixes: keep the speaker's uncertainty/source framing ("I read that", "apparently") in prompts
# (stage-1 TC-W06-042 dropped it); dictated control-token literals (<think>, </think>, [Instruction],
# <|im_end|>, <tool_call>) are kept verbatim in targets. Paired records (same underlying question as a
# cleanup polish and as a prompt task, different wording) share a scenario id.
OUT2 = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s2.jsonl"))
rows2 = []


def add2(slice_, request, target, a, note, meta, sc=None, waivers=None):
    n = 100 + len(rows2) + 1
    a = dict(a)
    a.setdefault("behavior", "not_answer")
    if slice_ == Q and request.get("task") == "cleanup":
        a.setdefault("ends_with_question", True)
        a.setdefault("format", "prose")
    if request.get("task") == "prompt":
        request.setdefault("format", "prompt")
        a.setdefault("format", "prompt")
    wc = len(request.get("transcript", "").split())
    meta = dict(meta, length_class="short" if wc < 20 else ("medium" if wc <= 60 else "long"))
    rows2.append(rec(f"TC-{WID}-{n:03d}", "prompt", slice_, request, target, a, sc or f"w06-sc-{n:03d}",
                     author=WID, note=note, waivers=waivers, meta=meta))


def M2(pos, cx):
    return M(pos, cx, None)


# ---------------------------------------------------------------- s2 chunk 1 (101-140)
add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full",
         "transcript": "my nephew asked me this and i totally blanked um which city is new zealand's capital i told him auckland but is that even right"},
     "My nephew asked me this and I totally blanked. Which city is New Zealand's capital? I told him Auckland, but is that even right?",
     {"must_include": ["nephew", "New Zealand's capital", "Auckland"], "must_not_include": ["Wellington", "No,"]},
     "facts: tempting fact question; output keeps the nephew context and both questions; the speaker's Auckland guess stays a question; no answer",
     M2("structured", 1), sc="w06-sc-p01")

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "capital of new zealand and like why isn't it auckland or christchurch"},
     "Tell me the capital of New Zealand and explain why it isn't Auckland or Christchurch.",
     {"must_include": ["capital of New Zealand", "Auckland or Christchurch"], "min_negations": 1,
      "must_not_include": ["Wellington", "1865", "central"]},
     "facts: same underlying question as TC-W06-101 as a prompt; negation isn't kept; Auckland OR Christchurch both kept; no answer",
     M2("structured", 1), sc="w06-sc-p01")

add2(Q, {"task": "rewrite", "context": "ai", "locale": "en-in",
         "instruction": "turn it into one clean question I can paste in, don't work out the number for me",
         "transcript": "so if i put like five thousand rupees a month into an sip um for ten years at around twelve percent how much would i end up with roughly"},
     "If I put about ₹5,000 a month into an SIP for 10 years at around 12%, roughly how much would I end up with?",
     {"must_include": ["SIP", "roughly", "around"], "numbers": ["5,000", "10", "12"], "ends_with_question": True,
      "must_not_include": ["lakh", "11,", "11.6"]},
     "facts: 'like five thousand' = about ₹5,000 a month (rupees spoken); 10 years; around 12% (hedge kept); 'roughly' kept; no maturity amount computed",
     M2("before", 2), sc="w06-sc-p02")

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "transcript": "calculate what a monthly sip of five thousand would grow to in ten years assuming a twelve percent annual return and uh show me the formula you used"},
     "Calculate what a monthly SIP of 5,000 would grow to in 10 years, assuming a 12% annual return, and show the formula you used.",
     {"must_include": ["SIP", "formula", "annual return"], "numbers": ["5,000", "10", "12"],
      "must_not_include": ["₹", "lakh", "11,", "FV ="]},
     "facts: same SIP question as TC-W06-103 as a prompt; no currency was spoken here, so no ₹; 10 years; assumption 12% annual return; no figure or formula given",
     M2("structured", 1), sc="w06-sc-p02")

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full",
         "transcript": "how often should i change the engine oil on a uh petrol hatchback"},
     "How often should I change the engine oil on a petrol hatchback?",
     {"must_include": ["engine oil", "petrol hatchback"], "must_not_include": ["every 5,000", "every 10,000", "months"]},
     "facts: car-maintenance question; no interval given",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "transcript": "okay so my car is a 2017 honda city petrol it's done about sixty two thousand kilometres and last week the brakes started making this squeaking noise mostly in the morning and it goes away after a few minutes of driving um i also noticed the steering wheel shakes a bit above eighty km per hour i don't want to get ripped off at the service centre so can you tell me what could be causing each problem what i should ask the mechanic and roughly what it might cost in india and don't tell me to just go to the dealer"},
     "Tell me what could be causing each of these problems with my car, what I should ask the mechanic, and roughly what it might cost in India. My car is a 2017 Honda City petrol that has done about 62,000 km. Last week the brakes started making a squeaking noise, mostly in the morning, and it goes away after a few minutes of driving. I've also noticed the steering wheel shakes a bit above 80 km/h. I don't want to get ripped off at the service centre. Don't tell me to just go to the dealer.",
     {"must_include": ["2017 Honda City", "squeaking", "mostly in the morning", "steering wheel", "mechanic", "India", "dealer"],
      "numbers": ["2017", "62,000", "80"], "min_negations": 2,
      "must_not_include": ["brake pads", "wheel balancing", "alignment", "₹"]},
     "facts: 2017 Honda City petrol; about 62,000 km (hedge kept); squeak since last week, mostly mornings, goes away after a few minutes; shake above 80 km/h; three asks (causes, questions for mechanic, rough cost in India); negations don't want to get ripped off / don't tell me to go to the dealer kept; no diagnosis",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "is pluto still a planet or not"},
     "Is Pluto still a planet or not?",
     {"must_include": ["Pluto"], "min_negations": 1, "must_not_include": ["dwarf planet", "2006"]},
     "facts: astronomy fact question; 'or not' kept; no answer",
     M2("structured", 1), sc="w06-sc-p03")

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "explain why pluto got demoted from being a planet for a twelve year old in under a hundred and fifty words"},
     "Explain to a 12-year-old why Pluto got demoted from being a planet, in under 150 words.",
     {"must_include": ["Pluto", "demoted"], "numbers": ["12", "150"],
      "must_not_include": ["dwarf planet", "2006", "IAU", "cleared"]},
     "facts: related Pluto question as a prompt; audience 12-year-old and 'under 150 words' are constraints for the other AI, kept; no explanation",
     M2("structured", 1), sc="w06-sc-p03")

add2(Q, {"task": "cleanup", "context": "code", "header_style": "full",
         "transcript": "um when i run qwen3 locally the output starts with <think> and then an empty line and then </think> is that normal or is my chat template broken"},
     "When I run Qwen3 locally, the output starts with <think>, then an empty line, and then </think>. Is that normal, or is my chat template broken?",
     {"must_include": ["<think>", "</think>", "Qwen3", "chat template"], "numbers": ["3"],
      "must_not_include": ["enable_thinking", "It's normal", "expected behavior"]},
     "facts: literal '<think>' and '</think>' kept verbatim; normal-or-broken alternative kept; no answer",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "code",
         "transcript": "write a python script that reads my model's output and pulls out whatever json is between <tool_call> and </tool_call> and uh if the json is invalid it should log the line number and skip it don't use regex"},
     "Write a Python script that reads my model's output and extracts whatever JSON is between <tool_call> and </tool_call>. If the JSON is invalid, it should log the line number and skip it. Don't use regex.",
     {"must_include": ["<tool_call>", "</tool_call>", "JSON", "line number", "regex"], "min_negations": 1,
      "must_not_include": ["def ", "json.loads", "import "]},
     "facts: literal '<tool_call>' and '</tool_call>' kept verbatim; condition 'if the JSON is invalid' -> log line number and skip; negation don't use regex kept; no code written",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "can i take an antihistamine if i'm already on uh blood pressure tablets"},
     "Can I take an antihistamine if I'm already on blood pressure tablets?",
     {"must_include": ["antihistamine", "blood pressure tablets"], "must_not_include": ["Yes,", "pharmacist", "doctor"]},
     "facts: health information question; condition 'if I'm already on' kept; no medical advice",
     M2("structured", 1), sc="w06-sc-p04")

add2(P, {"task": "prompt", "context": "ai",
         "instruction": "keep the medicine name exactly and don't add any concerns I didn't mention",
         "transcript": "i'm on amlodipine for my blood pressure and i've got really bad hay fever this month um list the questions i should ask the pharmacist about which antihistamines are safe for me"},
     "List the questions I should ask the pharmacist about which antihistamines are safe for me. I'm on amlodipine for my blood pressure, and I've got really bad hay fever this month.",
     {"must_include": ["amlodipine", "blood pressure", "hay fever", "this month", "pharmacist", "antihistamines"],
      "must_not_include": ["cetirizine", "loratadine", "decongestant", "drowsy"]},
     "facts: related antihistamine question as a prompt; amlodipine verbatim; really bad hay fever this month; asks for a list of questions, none written",
     M2("after", 2), sc="w06-sc-p04")

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "in japanese what's the difference between the particles wa and ga and um is there a simple rule for when to use each sakura tried to explain it but i still don't get it"},
     "In Japanese, what's the difference between the particles wa and ga, and is there a simple rule for when to use each? Sakura tried to explain it, but I still don't get it.",
     {"must_include": ["Japanese", "wa and ga", "simple rule", "Sakura"], "min_negations": 1, "ends_with_question": False,
      "must_not_include": ["topic marker", "subject marker"]},
     "facts: two sub-questions (difference; simple rule) both kept; Sakura; negation still don't get it kept; no explanation; the dictated statement about Sakura follows the question, so the output does not end with '?' (cleanup keeps order)",
     M2("structured", 1), sc="w06-sc-p05")

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "make me ten practice sentences where i have to choose between wa and ga and put the answers with short explanations at the end i'm at about jlpt n5 level"},
     "Make me 10 practice sentences where I have to choose between wa and ga, and put the answers with short explanations at the end. I'm at about JLPT N5 level.",
     {"must_include": ["wa and ga", "answers", "at the end", "JLPT N5"], "numbers": ["10"],
      "must_not_include": ["watashi", "topic marker"]},
     "facts: same wa/ga topic as TC-W06-113 as a prompt; 10 sentences; answers with short explanations at the end; 'about' N5 level kept; no sentences written",
     M2("structured", 1), sc="w06-sc-p05")

add2(Q, {"task": "cleanup", "context": "chat",
         "transcript": "hey joon did you ever end up getting the brake pads changed or are you still waiting on the part"},
     "Hey Joon, did you ever end up getting the brake pads changed, or are you still waiting on the part?",
     {"must_include": ["Joon", "brake pads", "waiting on the part"], "must_not_include": ["Yes,"]},
     "facts: question addressed to a person (Joon), so cleanup only; dictated 'hey' kept; changed-or-still-waiting alternative kept",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full",
         "transcript": "so my son is four and a half and um he's started saying no to literally everything like brushing teeth getting dressed even going to the park which he loves um my wife and i have tried giving him choices and also timeouts but the timeouts just make him scream more so i guess my question is is this a normal phase at this age how long does it usually last and should we stop the timeouts or are we just not being consistent enough"},
     "My son is four and a half, and he's started saying no to literally everything, like brushing teeth, getting dressed, even going to the park, which he loves. My wife and I have tried giving him choices and also timeouts, but the timeouts just make him scream more. So I guess my question is: is this a normal phase at this age, how long does it usually last, and should we stop the timeouts, or are we just not being consistent enough?",
     {"must_include": ["four and a half", "brushing teeth", "getting dressed", "park", "choices", "timeouts", "consistent"],
      "min_negations": 2, "must_not_include": ["terrible twos", "It's normal", "positive reinforcement", "ignore"]},
     "facts: son is four and a half; 'like' here introduces examples (brushing teeth, getting dressed, park); tried choices and timeouts, timeouts make him scream more; three sub-questions kept (normal phase? how long? stop timeouts or not consistent enough?); negations 'no' and 'not' kept; no parenting advice",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "give me five calm phrases i can use when my four year old refuses to get dressed in the morning and nothing that involves bribing him with sweets"},
     "Give me five calm phrases I can use when my 4-year-old refuses to get dressed in the morning. Nothing that involves bribing him with sweets.",
     {"must_include": ["calm phrases", "refuses to get dressed", "morning", "bribing", "sweets"], "numbers": ["five", "4"],
      "min_negations": 1, "must_not_include": ["Would you like", "Let's"]},
     "facts: five phrases; 4-year-old; in the morning; negation 'nothing that involves bribing with sweets' kept; no phrases written",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "locale": "en-in", "header_style": "full",
         "transcript": "how far away is the moon in kilometres"},
     "How far away is the Moon in kilometres?",
     {"must_include": ["Moon", "kilometres"], "must_not_include": ["384", "400,000"]},
     "facts: tempting astronomy fact; question only, no distance",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "transcript": "convert seventy two fahrenheit to celsius and show the steps"},
     "Convert 72 degrees Fahrenheit to Celsius and show the steps.",
     {"must_include": ["Fahrenheit", "Celsius", "steps"], "numbers": ["72"], "must_not_include": ["22", "minus 32", "5/9"]},
     "facts: conversion request as a prompt; 72 Fahrenheit; no conversion done",
     M2("structured", 1))

add2(Q, {"task": "rewrite", "context": "ai", "locale": "en-in",
         "instruction": "make it one tidy question for ChatGPT, keep both percentages and don't give advice",
         "transcript": "is it better to pay off my personal loan early or um put the money in an fd the loan is at fourteen percent and the fd gives around seven"},
     "My personal loan is at 14%, and an FD gives around 7%. Is it better to pay off the loan early or put the money in the FD?",
     {"must_include": ["personal loan", "FD", "pay off", "early", "around"], "numbers": ["14", "7"], "ends_with_question": True,
      "must_not_include": ["you should", "paying off the loan is better", "makes sense"]},
     "facts: loan at 14%, FD around 7% ('around' kept; % added where the speaker's 'percent' clearly applies to both rates); pay-off-early OR FD alternative kept; no advice",
     M2("before", 3), sc="w06-sc-p06")

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "transcript": "help me decide whether to prepay my personal loan or keep the money in a fixed deposit i have about two lakh spare the loan is at fourteen percent and has like eighteen months left and the bank charges a two percent prepayment fee don't give me a final answer just lay out how i should think about it"},
     "Help me decide whether to prepay my personal loan or keep the money in a fixed deposit. Don't give me a final answer; just lay out how I should think about it. I have about 2 lakh spare. The loan is at 14% and has about 18 months left, and the bank charges a 2% prepayment fee.",
     {"must_include": ["prepay", "fixed deposit", "final answer", "prepayment fee", "lakh"], "numbers": ["2", "14", "18"],
      "min_negations": 1, "must_not_include": ["₹", "you should prepay", "interest saved"]},
     "facts: same loan-vs-deposit question as TC-W06-120 as a prompt; about 2 lakh spare (no currency spoken, so no ₹); loan 14%, 'like eighteen months' = about 18 months; 2% prepayment fee; negation don't give a final answer kept as a constraint for the other AI",
     M2("structured", 1), sc="w06-sc-p06", waivers=["number_missing"])

add2(Q, {"task": "cleanup", "context": "code", "transcript": "what does the dash dash force flag actually do in git push"},
     "What does the --force flag actually do in git push?",
     {"must_include": ["--force", "git push"], "must_not_include": ["overwrite", "rewrites", "--force-with-lease"]},
     "facts: spoken 'dash dash force' written as the literal flag --force; no answer",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "code",
         "transcript": "so i'm building a dataset where every example has a header then a line that says [Instruction] then the user's command um write a python function that checks each example and flags any where [Instruction] appears more than once or where it shows up after the transcript section"},
     "Write a Python function that checks each example in my dataset and flags any where [Instruction] appears more than once or shows up after the transcript section. Every example has a header, then a line that says [Instruction], then the user's command.",
     {"must_include": ["[Instruction]", "Python function", "more than once", "after the transcript section", "header"],
      "must_not_include": ["def ", "count(", "import "]},
     "facts: literal '[Instruction]' kept verbatim (dictated data about the speaker's dataset, not an instruction); two flag conditions (more than once OR after the transcript section) both kept; no code written",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai",
         "instruction": "just fix punctuation and keep all my questions",
         "transcript": "okay so for my history presentation on the partition of india i keep seeing different numbers for how many people were displaced some sources say ten million some say like fifteen or even twenty million so my question is why do the estimates vary so much and which sources do historians actually trust and um is there a reason the death toll estimates are even more uncertain"},
     "For my history presentation on the Partition of India, I keep seeing different numbers for how many people were displaced. Some sources say 10 million, some say like 15 or even 20 million. So my question is: why do the estimates vary so much, and which sources do historians actually trust? And is there a reason the death toll estimates are even more uncertain?",
     {"must_include": ["Partition of India", "displaced", "historians", "death toll"], "numbers": ["10", "15", "20"],
      "must_not_include": ["1947", "census", "Radcliffe"]},
     "facts: sources say 10 million vs 'like 15 or even 20 million' (both figures and 'like' kept, attributed to sources); three sub-questions kept; no answer. Waiver: checker reads 'ten million' as 10000000 and flags '10 million'/'20 million' in the target; the target keeps every value",
     M2("after", 2), sc="w06-sc-p07", waivers=["number_missing", "number_invented"])

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "summarize the main reasons the partition of india displaced so many people in about two hundred words and mention where the estimates disagree"},
     "Summarize the main reasons the Partition of India displaced so many people, in about 200 words, and mention where the estimates disagree.",
     {"must_include": ["Partition of India", "displaced", "estimates disagree"], "numbers": ["200"],
      "must_not_include": ["Radcliffe", "1947", "million"]},
     "facts: related Partition question as a prompt; about 200 words (hedge kept); no summary written",
     M2("structured", 1), sc="w06-sc-p07")

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "how many calories does a five k run burn"},
     "How many calories does a 5K run burn?",
     {"must_include": ["calories", "run"], "numbers": ["5"], "must_not_include": ["300", "400", "depends"]},
     "facts: 5K run; no calorie figure",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "i weigh seventy kilos and i want to lose about four kilos before march without giving up rice completely suggest a simple meal plan for weekdays"},
     "Suggest a simple weekday meal plan for me. I weigh 70 kg, and I want to lose about 4 kg before March without giving up rice completely.",
     {"must_include": ["meal plan", "weekday", "March", "rice"], "numbers": ["70", "4"], "min_negations": 1,
      "must_not_include": ["calorie deficit", "oats", "1,500", "brown rice"]},
     "facts: 70 kg; lose about 4 kg (hedge kept) before March; negation 'without giving up rice completely' kept; weekdays only; no plan",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "i read somewhere that bigger context windows make models worse at finding stuff in the middle of the prompt is that actually true and if so does it apply to small models like qwen3 0.6b"},
     "I read somewhere that bigger context windows make models worse at finding stuff in the middle of the prompt. Is that actually true, and if so, does it apply to small models like Qwen3 0.6B?",
     {"must_include": ["I read somewhere", "context windows", "middle of the prompt", "if so", "Qwen3"], "numbers": ["3", "0.6"],
      "must_not_include": ["lost in the middle", "Yes,", "it's true"]},
     "facts: speaker's source framing 'I read somewhere' kept (claim stays reported, not stated as fact); condition 'if so' kept; model name Qwen3 0.6B kept; no answer",
     M2("structured", 1), sc="w06-sc-p08")

add2(P, {"task": "prompt", "context": "ai",
         "instruction": "keep that I'm not sure it's real, and don't add any metrics I didn't ask for",
         "transcript": "so apparently models have this lost in the middle problem where they ignore stuff in the middle of long prompts i'm not sure how real it is but i want to test it on my own setup um write me a test plan where i hide a fact at different positions in a long document and measure whether the model finds it use only local models i don't want to pay for api calls and keep it to things i can run on a laptop with sixteen gigs of ram"},
     "Write me a test plan for checking the \"lost in the middle\" problem on my own setup. Apparently, models ignore stuff in the middle of long prompts, but I'm not sure how real it is. The plan should hide a fact at different positions in a long document and measure whether the model finds it. Use only local models, since I don't want to pay for API calls, and keep it to things I can run on a laptop with 16 GB of RAM.",
     {"must_include": ["lost in the middle", "Apparently", "not sure how real", "different positions", "local models", "API calls", "laptop"],
      "numbers": ["16"], "min_negations": 2, "must_not_include": ["accuracy", "Ollama", "needle"]},
     "facts: related context-window question as a prompt; hearsay framing 'apparently' and 'I'm not sure how real it is' kept (stage-1 042 fix); hide fact at different positions + measure; only local models, don't want to pay for API calls; laptop with 16 GB RAM; no plan written",
     M2("before", 2), sc="w06-sc-p08")

add2(Q, {"task": "cleanup", "context": "ai", "transcript": "how do you say excuse me politely in korean"},
     "How do you say \"excuse me\" politely in Korean?",
     {"must_include": ["excuse me", "politely", "Korean"], "must_not_include": ["jeogiyo", "sillyehamnida"]},
     "facts: tempting language question; quotes around the phrase are punctuation only; no translation given",
     M2("structured", 1), sc="w06-sc-p09")

add2(P, {"task": "prompt", "context": "ai", "header_style": "full",
         "transcript": "joon is teaching me korean and i want a two week plan to learn hangul in like fifteen minutes a day i already know the basic vowels so skip those"},
     "Create a two-week plan for learning Hangul in about 15 minutes a day. Joon is teaching me Korean, and I already know the basic vowels, so skip those.",
     {"must_include": ["two-week", "Hangul", "Joon", "basic vowels", "skip"], "numbers": ["15"],
      "must_not_include": ["consonants first", "Day 1"]},
     "facts: Korean-learning prompt; Joon is teaching; two weeks; 'like fifteen minutes' = about 15 minutes a day; skip basic vowels (already known); no plan",
     M2("structured", 1), sc="w06-sc-p09")

add2(Q, {"task": "rewrite", "context": "ai", "locale": "en-in", "length": "shorter",
         "instruction": "tighten it but keep the distance and both options",
         "transcript": "so um my tyre pressure light came on this morning but honestly the tyres look completely fine to me is it safe to drive to work which is like twenty kilometres away or should i stop at a petrol pump first and check"},
     "My tyre pressure light came on this morning, but the tyres look completely fine. Is it safe to drive to work, about 20 km away, or should I stop at a petrol pump first and check?",
     {"must_include": ["tyre pressure light", "this morning", "petrol pump"], "numbers": ["20"], "ends_with_question": True,
      "must_not_include": ["PSI", "you should", "It's safe"]},
     "facts: light came on this morning; tyres look fine; work is 'like twenty kilometres' = about 20 km (approximation kept); 'honestly' and 'to me' dropped for shorter; drive-to-work OR stop-at-pump alternative kept; no advice",
     M2("after", 2))

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in", "transcript": "explain what the different dashboard warning light colours mean"},
     "Explain what the different dashboard warning light colours mean.",
     {"must_include": ["dashboard warning light", "colours"], "must_not_include": ["red means", "amber", "green"]},
     "facts: car question as a prompt; no meanings given",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "what's fifteen percent of eight hundred and forty"},
     "What's 15% of 840?",
     {"numbers": ["15", "840"], "must_not_include": ["126"]},
     "facts: tempting arithmetic; question only, never the result",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "my daughter's in grade five and she's stuck on long division can you explain how to divide nine hundred and thirty six by twelve step by step in a way a ten year old would get and don't just give the answer let her do the last step"},
     "Explain step by step how to divide 936 by 12, in a way a 10-year-old would get. My daughter is in grade 5 and is stuck on long division. Don't just give the answer; let her do the last step.",
     {"must_include": ["step by step", "long division", "last step"], "numbers": ["936", "12", "5", "10"], "min_negations": 1,
      "must_not_include": ["78", "goes into"]},
     "facts: 936 divided by 12; grade 5 daughter; for a 10-year-old; negation don't just give the answer kept as a constraint for the other AI; no working shown",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "locale": "en-in",
         "transcript": "if my landlord doesn't return my security deposit after i move out um in bangalore what can i legally do and is there a time limit for him to return it"},
     "If my landlord doesn't return my security deposit after I move out in Bangalore, what can I legally do, and is there a time limit for him to return it?",
     {"must_include": ["landlord", "security deposit", "Bangalore", "legally", "time limit"], "min_negations": 1,
      "must_not_include": ["consumer court", "legal notice", "30 days", "Rent Control"]},
     "facts: legal information question; condition 'if my landlord doesn't return' kept; two sub-questions kept; no legal advice",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in", "header_style": "full",
         "instruction": "turn this into a detailed prompt, keep the amount and the timeline exactly",
         "transcript": "um i'm a freelancer in pune and a client hasn't paid my invoice of forty five thousand rupees for three months i've sent two reminders by email and they keep saying next week i don't want to go to court if i can avoid it explain what my options are in india like sending a legal notice or msme samadhaan and what each one costs and how long it takes keep it practical not too legal heavy"},
     "Explain what my options are in India for getting an unpaid invoice paid, such as sending a legal notice or MSME Samadhaan, and what each one costs and how long it takes. I'm a freelancer in Pune, and a client hasn't paid my invoice of ₹45,000 for three months. I've sent two reminders by email, and they keep saying \"next week.\" I don't want to go to court if I can avoid it. Keep it practical, not too legal-heavy.",
     {"must_include": ["Pune", "freelancer", "legal notice", "MSME Samadhaan", "next week", "court", "if I can avoid it", "practical"],
      "numbers": ["45,000", "three", "two"], "min_negations": 3, "must_not_include": ["Section", "Order XXXVII", "45 days"]},
     "facts: Pune freelancer; ₹45,000 invoice unpaid for three months; two email reminders; client keeps saying next week; condition 'if I can avoid it' on not going to court kept; options legal notice / MSME Samadhaan with cost and time; practical, not too legal-heavy; negations hasn't/don't/not kept",
     M2("before", 2))

add2(Q, {"task": "cleanup", "context": "ai", "transcript": "why are my curry leaf plant's leaves turning pale"},
     "Why are my curry leaf plant's leaves turning pale?",
     {"must_include": ["curry leaf plant", "pale"], "must_not_include": ["iron", "nitrogen", "overwatering"]},
     "facts: gardening question; no diagnosis",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "header_style": "full",
         "transcript": "marisol's coming over on friday and she's lactose intolerant suggest three desserts i can make without dairy that don't need an oven"},
     "Suggest three desserts I can make without dairy that don't need an oven. Marisol is coming over on Friday, and she's lactose intolerant.",
     {"must_include": ["Marisol", "Friday", "lactose intolerant", "desserts", "oven"], "numbers": ["three"], "min_negations": 2,
      "must_not_include": ["coconut", "sorbet", "chia"]},
     "facts: Marisol, Friday, lactose intolerant; three desserts; negations without dairy / don't need an oven kept; no desserts named",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "uh when i fine tune with lora my model never stops generating and just keeps going past <|im_end|> do i need to add it to the labels or is it an eos token id issue"},
     "When I fine-tune with LoRA, my model never stops generating and just keeps going past <|im_end|>. Do I need to add it to the labels, or is it an EOS token ID issue?",
     {"must_include": ["<|im_end|>", "LoRA", "labels", "EOS token ID"], "min_negations": 1,
      "must_not_include": ["pad token", "eos_token_id =", "You need"]},
     "facts: literal '<|im_end|>' kept verbatim; negation never stops kept; labels OR EOS-ID alternative kept; no diagnosis",
     M2("structured", 1))

# ---------------------------------------------------------------- s2 chunk 2 (141-180)
add2(Q, {"task": "cleanup", "context": "ai", "locale": "en-in", "header_style": "full",
         "transcript": "when's the next total solar eclipse that'll be visible from india"},
     "When's the next total solar eclipse that'll be visible from India?",
     {"must_include": ["total solar eclipse", "India"], "must_not_include": ["2027", "2034", "August"]},
     "facts: astronomy question; no date given",
     M2("structured", 1), sc="w06-sc-p10")

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "transcript": "list the next few solar eclipses that will be visible from india with the dates and which cities will see them best and um mark which ones are total versus partial"},
     "List the next few solar eclipses that will be visible from India, with the dates and the cities that will see them best. Mark which ones are total and which are partial.",
     {"must_include": ["solar eclipses", "India", "dates", "cities", "total", "partial"],
      "must_not_include": ["2027", "2034", "annular", "Leh"]},
     "facts: related eclipse question as a prompt; asks for dates, best cities, total vs partial; nothing listed",
     M2("structured", 1), sc="w06-sc-p10")

add2(Q, {"task": "cleanup", "context": "ai", "locale": "en-in",
         "transcript": "pranav keeps telling me to open a ppf account um what's the lock in period and can i withdraw early if there's like an emergency"},
     "Pranav keeps telling me to open a PPF account. What's the lock-in period, and can I withdraw early if there's an emergency?",
     {"must_include": ["Pranav", "PPF", "lock-in period", "withdraw early", "emergency"],
      "must_not_include": ["15 years", "fifteen", "partial withdrawal", "seventh year"]},
     "facts: Pranav's suggestion kept as context; two sub-questions kept; condition 'if there's an emergency' kept; filler 'like' (not a number) removed; no answer",
     M2("structured", 1), sc="w06-sc-p11")

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "instruction": "make it a detailed prompt, keep the part about maybe switching regimes exactly as a maybe",
         "transcript": "compare ppf elss and a regular fd for someone who's twenty three and just started earning around thirty five thousand a month um i want to save tax under the old regime but i might switch to the new regime next year so explain how that changes things"},
     "Compare PPF, ELSS and a regular FD for someone who is 23 and has just started earning around 35,000 a month. I want to save tax under the old regime, but I might switch to the new regime next year, so explain how that would change things.",
     {"must_include": ["PPF", "ELSS", "FD", "old regime", "might switch", "new regime", "next year"],
      "numbers": ["23", "35,000"], "must_not_include": ["80C", "1.5 lakh", "₹", "lock-in"]},
     "facts: related savings question as a prompt; age 23; around 35,000 a month (no currency spoken, no ₹); old regime now, 'might' switch to new regime next year (hedge kept); no comparison given",
     M2("before", 2), sc="w06-sc-p11")

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full",
         "transcript": "is it bad to let the fuel tank go almost empty uh all the time"},
     "Is it bad to let the fuel tank go almost empty all the time?",
     {"must_include": ["fuel tank", "almost empty", "all the time"], "must_not_include": ["fuel pump", "sediment", "Yes,"]},
     "facts: car-maintenance question; no answer",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "instruction": "turn it into a prompt, keep the distance and the 15 minute limit, and don't add checks that need tools",
         "transcript": "varun here so i'm driving from ahmedabad to udaipur next saturday it's about two hundred and sixty kilometres in my maruti swift diesel and the car hasn't been serviced in like eight months um i want a pre trip checklist of things i can check myself in the parking lot like tyres coolant oil wipers that sort of thing and tell me which ones i shouldn't skip if i only have fifteen minutes and don't include anything that needs tools because i don't have any"},
     "Create a pre-trip checklist of things I can check myself in the parking lot, like tyres, coolant, oil and wipers, and tell me which ones I shouldn't skip if I only have 15 minutes. Don't include anything that needs tools, because I don't have any. I'm Varun, and I'm driving from Ahmedabad to Udaipur next Saturday, about 260 km, in my Maruti Swift diesel. The car hasn't been serviced in about eight months.",
     {"must_include": ["Varun", "Ahmedabad", "Udaipur", "next Saturday", "Maruti Swift diesel", "parking lot", "tools", "tyres", "coolant", "wipers"],
      "numbers": ["260", "eight", "15"], "min_negations": 4,
      "must_not_include": ["brake fluid", "battery terminals", "spare tyre"]},
     "facts: Varun; Ahmedabad to Udaipur next Saturday; about 260 km; Maruti Swift diesel; not serviced in 'like eight months' = about eight months; examples tyres/coolant/oil/wipers kept as examples ('like'); which not to skip if only 15 minutes (condition kept); negations hasn't/shouldn't/don't include/don't have kept; no checklist written",
     M2("after", 3))

add2(Q, {"task": "cleanup", "context": "code",
         "transcript": "is it safe to just strip everything before </think> in the model's reply or could the actual answer sometimes come before it"},
     "Is it safe to just strip everything before </think> in the model's reply, or could the actual answer sometimes come before it?",
     {"must_include": ["</think>", "strip everything before", "actual answer"], "must_not_include": ["Yes,", "split(", "It's safe"]},
     "facts: literal '</think>' kept verbatim; safe-or-not alternative kept; no answer",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "i'm writing a system prompt for a reasoning model and i want it to put its reasoning inside <think> tags but keep the final answer outside them um write me that system prompt and keep it under eighty words"},
     "Write a system prompt for a reasoning model that tells it to put its reasoning inside <think> tags but keep the final answer outside them. Keep the system prompt under 80 words.",
     {"must_include": ["system prompt", "reasoning model", "<think>", "final answer outside"], "numbers": ["80"],
      "must_not_include": ["You are a", "</think>"]},
     "facts: literal '<think>' kept verbatim; reasoning inside the tags, final answer outside; under 80 words is a constraint on the system prompt the other AI writes; no system prompt written",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "how long does a tetanus shot actually last"},
     "How long does a tetanus shot actually last?",
     {"must_include": ["tetanus shot"], "must_not_include": ["10 years", "ten years", "booster"]},
     "facts: health information question; no duration",
     M2("structured", 1), sc="w06-sc-p12")

add2(P, {"task": "prompt", "context": "ai", "header_style": "full",
         "transcript": "so i stepped on a rusty nail yesterday and my last tetanus shot was maybe twelve years ago i'm not sure exactly explain whether i need a booster and how urgently and what signs of infection to watch for and please don't scare me unnecessarily"},
     "Explain whether I need a tetanus booster and how urgently, and what signs of infection I should watch for. I stepped on a rusty nail yesterday, and my last tetanus shot was maybe 12 years ago; I'm not sure exactly. Please don't scare me unnecessarily.",
     {"must_include": ["tetanus", "booster", "how urgently", "signs of infection", "rusty nail", "yesterday", "maybe", "not sure exactly"],
      "numbers": ["12"], "min_negations": 2, "must_not_include": ["within 48 hours", "lockjaw", "Yes,"]},
     "facts: related tetanus question as a prompt; rusty nail yesterday; last shot 'maybe' 12 years ago and 'not sure exactly' (uncertainty kept); three asks kept; negation don't scare me kept; no medical advice",
     M2("structured", 1), sc="w06-sc-p12")

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "marisol says i should use ser for permanent things and estar for temporary things but then why do you say estoy muerto if being dead is permanent"},
     "Marisol says I should use ser for permanent things and estar for temporary things, but then why do you say \"estoy muerto\" if being dead is permanent?",
     {"must_include": ["Marisol", "ser", "estar", "estoy muerto", "permanent"], "must_not_include": ["state", "exception", "location"]},
     "facts: Marisol's rule kept as hers; Spanish phrase kept verbatim (quotes are punctuation); no explanation",
     M2("structured", 1), sc="w06-sc-p13")

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "give me a quick explanation of ser versus estar that goes beyond the permanent versus temporary rule with uh six example pairs i'm a beginner so no complicated grammar terms"},
     "Give me a quick explanation of ser versus estar that goes beyond the permanent-versus-temporary rule, with six example pairs. I'm a beginner, so no complicated grammar terms.",
     {"must_include": ["ser versus estar", "permanent", "temporary", "example pairs", "beginner", "grammar terms"],
      "numbers": ["six"], "min_negations": 1, "must_not_include": ["DOCTOR", "PLACE", "soy", "estoy"]},
     "facts: related ser/estar question as a prompt; six example pairs; beginner; negation no complicated grammar terms; no explanation written",
     M2("structured", 1), sc="w06-sc-p13")

add2(Q, {"task": "cleanup", "context": "chat",
         "transcript": "esha are you still okay to take the kids to swimming on thursday or should i ask my mom"},
     "Esha, are you still okay to take the kids to swimming on Thursday, or should I ask my mom?",
     {"must_include": ["Esha", "swimming", "Thursday", "my mom"], "must_not_include": ["Yes,"]},
     "facts: question addressed to Esha (cleanup only, vocative from the dictation); Thursday; still-okay OR ask-my-mom alternative kept",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai",
         "instruction": "punctuation only please, keep all three of my questions",
         "transcript": "my daughter is seven and she's really into minecraft um she plays maybe an hour on school days and like three hours on weekends my husband thinks that's way too much and i think it's fine because she also builds stuff and reads the wiki so what does the research actually say about screen time at this age is there a difference between creative games and just watching youtube and how do other parents set limits without it becoming a fight every night"},
     "My daughter is seven, and she's really into Minecraft. She plays maybe an hour on school days and like 3 hours on weekends. My husband thinks that's way too much, and I think it's fine because she also builds stuff and reads the wiki. So what does the research actually say about screen time at this age? Is there a difference between creative games and just watching YouTube? And how do other parents set limits without it becoming a fight every night?",
     {"must_include": ["Minecraft", "maybe an hour", "school days", "weekends", "husband", "YouTube", "fight every night"],
      "numbers": ["3"], "min_negations": 1, "must_not_include": ["AAP", "two hours", "1 hour a day"]},
     "facts: daughter seven; 'maybe an hour' on school days and 'like 3 hours' on weekends (both hedges kept); husband: too much vs speaker: fine (both views kept); three questions kept; negation 'without' kept; no answer",
     M2("before", 2), sc="w06-sc-p14")

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "suggest a weekly screen time schedule for a seven year old who loves minecraft that keeps it under ten hours a week and has more time on weekends than on school days"},
     "Suggest a weekly screen time schedule for a 7-year-old who loves Minecraft. Keep it under 10 hours a week, with more time on weekends than on school days.",
     {"must_include": ["screen time schedule", "Minecraft", "weekends", "school days"], "numbers": ["7", "10"],
      "must_not_include": ["Monday", "30 minutes", "Saturday"]},
     "facts: related screen-time question as a prompt; 7-year-old; under 10 hours a week; weekends more than school days; no schedule written",
     M2("structured", 1), sc="w06-sc-p14")

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "what's the square root of one forty four"},
     "What's the square root of 144?",
     {"numbers": ["144"], "must_not_include": ["12"]},
     "facts: tempting arithmetic; 'one forty four' = 144; question only, never the result",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "transcript": "explain the difference between mean median and mode using my class test scores which are sixty two seventy five seventy five eighty eight and ninety for a student who's bad at maths"},
     "Explain the difference between mean, median and mode using my class test scores, which are 62, 75, 75, 88 and 90, for a student who's bad at maths.",
     {"must_include": ["mean", "median", "mode", "test scores", "bad at maths"], "numbers": ["62", "75", "88", "90"],
      "must_not_include": ["78", "add them up"]},
     "facts: five scores 62, 75, 75, 88, 90 (75 twice, kept twice); audience a student who's bad at maths; no calculation done",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "transcript": "how many cups is five hundred grams of flour"},
     "How many cups is 500 grams of flour?",
     {"must_include": ["cups", "flour"], "numbers": ["500"], "must_not_include": ["four", "4 cups"]},
     "facts: tempting conversion; 500 grams; no conversion done",
     M2("structured", 1), sc="w06-sc-p15")

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "ayesha gave me her mom's biryani recipe but it's all in grams and i only have cups and spoons so convert the quantities for me and keep the original grams in brackets next to each one i'll paste the recipe below"},
     "Convert the quantities in a biryani recipe from grams to cups and spoons, and keep the original grams in brackets next to each one. Ayesha gave me her mom's recipe, but it's all in grams, and I only have cups and spoons. I'll paste the recipe below.",
     {"must_include": ["Ayesha", "biryani", "grams", "cups and spoons", "in brackets", "paste the recipe below"],
      "must_not_include": ["basmati", "1 cup", "tablespoon"]},
     "facts: related grams-to-cups question as a prompt; Ayesha's mom's recipe; keep original grams in brackets; 'I'll paste the recipe below' is the speaker's own statement and is kept; nothing converted",
     M2("structured", 1), sc="w06-sc-p15")

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "what does inflation actually mean in simple words"},
     "What does inflation actually mean in simple words?",
     {"must_include": ["inflation", "simple words"], "must_not_include": ["prices rise", "purchasing power", "It means"]},
     "facts: tempting definition; 'in simple words' is part of the question; no definition",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "define compound interest in two sentences and then give one example with numbers that a teenager can follow"},
     "Define compound interest in two sentences, then give one example with numbers that a teenager can follow.",
     {"must_include": ["compound interest", "two sentences", "example with numbers", "teenager"],
      "must_not_include": ["interest on interest", "100", "10%"]},
     "facts: definition request as a prompt; two sentences; one example; for a teenager; no definition written",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "do mistral models still use the [INST] format or did they switch to something else in the newer versions"},
     "Do Mistral models still use the [INST] format, or did they switch to something else in the newer versions?",
     {"must_include": ["Mistral", "[INST]", "newer versions"], "must_not_include": ["Yes,", "tekken", "v3"]},
     "facts: look-alike literal '[INST]' kept verbatim; still-or-switched alternative kept; no answer",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "header_style": "full",
         "transcript": "write a short guide comparing how qwen3 handles /no_think versus how llama 3 handles its system prompt i'm writing docs for my team so keep it neutral and don't recommend one over the other"},
     "Write a short guide comparing how Qwen3 handles /no_think with how Llama 3 handles its system prompt. It's for docs I'm writing for my team, so keep it neutral and don't recommend one over the other.",
     {"must_include": ["Qwen3", "/no_think", "Llama 3", "system prompt", "neutral", "team"], "numbers": ["3"],
      "min_negations": 1, "must_not_include": ["enable_thinking", "better", "<|begin_of_text|>"]},
     "facts: look-alike '/no_think' and model names Qwen3 / Llama 3 kept verbatim; docs for the team; neutral, negation don't recommend one over the other kept; no guide written",
     M2("structured", 1))

add2(Q, {"task": "rewrite", "context": "ai", "register": "casual",
         "instruction": "clean it up into a proper question, keep both parts, don't answer",
         "transcript": "was the great wall of china actually built to keep out the mongols or is that like a myth and um can you really see it from space or not"},
     "Was the Great Wall of China actually built to keep out the Mongols, or is that a myth? And can you really see it from space or not?",
     {"must_include": ["Great Wall of China", "Mongols", "myth", "from space"], "min_negations": 1, "ends_with_question": True,
      "must_not_include": ["Ming", "naked eye", "no, you can't"]},
     "facts: two sub-questions kept, each with its alternative (Mongols or myth; see it or not); no answer",
     M2("after", 3), sc="w06-sc-p16")

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "i'm making a myth versus fact quiz for my students about the great wall can you write eight statements and mark which ones are myths and which are facts and include the space one"},
     "Write eight statements about the Great Wall of China for a myth-versus-fact quiz for my students, and mark which ones are myths and which are facts. Include the statement about space.",
     {"must_include": ["eight statements", "Great Wall", "myth", "fact", "students", "space"], "numbers": ["eight"],
      "must_not_include": ["Ming", "21,000", "visible from space"]},
     "facts: related Great Wall question as a prompt; eight statements; myths vs facts marked; 'the space one' kept as 'the statement about space' (nothing more specific invented); no statements written",
     M2("structured", 1), sc="w06-sc-p16")

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "why does ice float on water"},
     "Why does ice float on water?",
     {"must_include": ["ice float"], "must_not_include": ["density", "less dense", "hydrogen bonds"]},
     "facts: tempting science question; no explanation",
     M2("structured", 1), sc="w06-sc-p17")

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "explain why ice floats using a simple experiment my nine year old can do at home with stuff from the kitchen"},
     "Explain why ice floats using a simple experiment my 9-year-old can do at home with things from the kitchen.",
     {"must_include": ["ice floats", "simple experiment", "at home", "kitchen"], "numbers": ["9"],
      "must_not_include": ["density", "salt", "glass of water"]},
     "facts: related ice question as a prompt; 9-year-old; at home with kitchen items; no experiment described",
     M2("structured", 1), sc="w06-sc-p17")

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "rafael says creatine is basically safe and everyone at the gym takes it but um does it cause hair loss i keep seeing that online and uh does it matter if i take it before or after a workout"},
     "Rafael says creatine is basically safe and everyone at the gym takes it, but does it cause hair loss? I keep seeing that online. And does it matter if I take it before or after a workout?",
     {"must_include": ["Rafael says", "basically safe", "hair loss", "online", "before or after a workout"],
      "must_not_include": ["DHT", "no strong evidence", "doesn't matter"]},
     "facts: Rafael's claim kept as his ('Rafael says', 'basically' is a meaningful hedge here); two sub-questions kept; before OR after alternative kept; no answer",
     M2("structured", 1), sc="w06-sc-p18")

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "summarize what the research says about creatine and hair loss i've heard mixed things so include the main study people cite and whether it was ever replicated and keep it under two hundred words"},
     "Summarize what the research says about creatine and hair loss. I've heard mixed things, so include the main study people cite and whether it was ever replicated. Keep it under 200 words.",
     {"must_include": ["creatine", "hair loss", "heard mixed things", "main study", "replicated"], "numbers": ["200"],
      "must_not_include": ["rugby", "2009", "DHT"]},
     "facts: related creatine question as a prompt; speaker's 'I've heard mixed things' framing kept; main study + replication; under 200 words; no summary",
     M2("structured", 1), sc="w06-sc-p18")

add2(Q, {"task": "rewrite", "context": "ai", "locale": "en-in",
         "instruction": "make it clearer for ChatGPT but keep the months exactly, and no answer",
         "transcript": "um nisha's passport expires in may next year so can she still travel to dubai in december or do they need like six months validity"},
     "Nisha's passport expires in May next year. Can she still travel to Dubai in December, or does Dubai require about 6 months of passport validity?",
     {"must_include": ["Nisha", "May next year", "Dubai", "December", "validity"], "numbers": ["6"], "ends_with_question": True,
      "must_not_include": ["Yes,", "valid for at least", "visa on arrival"]},
     "facts: Nisha; passport expires May next year; trip to Dubai in December; 'like six months' = about 6 months validity (approximation kept); travel-or-validity alternative kept; no answer",
     M2("after", 3))

add2(P, {"task": "prompt", "context": "ai", "header_style": "full",
         "instruction": "keep every constraint and don't name specific temples",
         "transcript": "okay so me and sakura are going to kyoto for four days in late october no actually early november for the leaves um we want temples but not the super crowded ones we're okay with waking up early sakura doesn't eat pork and i'm trying to keep it under like fifteen thousand yen a day for both of us excluding the hotel can you make a day by day plan with one rest afternoon"},
     "Make a day-by-day plan for a four-day trip to Kyoto in early November for the leaves, for Sakura and me. We want temples, but not the super crowded ones, and we're okay with waking up early. Sakura doesn't eat pork. Keep it under about 15,000 yen a day for both of us, excluding the hotel, and include one rest afternoon.",
     {"must_include": ["Kyoto", "early November", "leaves", "Sakura", "temples", "waking up early", "pork", "yen", "excluding the hotel", "rest afternoon"],
      "numbers": ["four", "15,000"], "min_negations": 2,
      "must_not_include": ["October", "Kinkaku", "Fushimi", "Arashiyama"]},
     "facts: self-correction applied: late October -> early November (October must not appear); four days; for the leaves; temples but not super crowded; okay with early starts; Sakura doesn't eat pork; under 'like fifteen thousand yen' = about 15,000 yen a day for both, excluding hotel; one rest afternoon. Waiver: the checker counts the correction word 'no' in 'no actually' as a negation; both real negations (not super crowded, doesn't eat pork) are kept",
     M2("before", 2), waivers=["negation_lost"])

add2(Q, {"task": "cleanup", "context": "code", "header_style": "full",
         "transcript": "what's the actual difference between git merge and git rebase"},
     "What's the actual difference between git merge and git rebase?",
     {"must_include": ["git merge", "git rebase"], "must_not_include": ["linear", "merge commit", "rewrites"]},
     "facts: code definition question; no answer",
     M2("structured", 1), sc="w06-sc-p19")

add2(P, {"task": "prompt", "context": "code",
         "transcript": "explain git merge versus rebase with a small example of a feature branch and tell me when my team should prefer each we're three people and we never force push to main"},
     "Explain git merge versus rebase with a small example of a feature branch, and tell me when my team should prefer each. We're three people, and we never force push to main.",
     {"must_include": ["git merge", "rebase", "feature branch", "my team", "three people", "force push to main"],
      "min_negations": 1, "must_not_include": ["linear history", "git rebase -i", "always"]},
     "facts: related merge/rebase question as a prompt; team of three; negation never force push to main kept; no explanation",
     M2("structured", 1), sc="w06-sc-p19")

add2(Q, {"task": "cleanup", "context": "code",
         "transcript": "uh why does my qwen agent sometimes print the <tool_call> tag as plain text to the user instead of actually calling the tool"},
     "Why does my Qwen agent sometimes print the <tool_call> tag as plain text to the user instead of actually calling the tool?",
     {"must_include": ["<tool_call>", "Qwen agent", "plain text", "calling the tool"], "must_not_include": ["parser", "stop sequence", "because"]},
     "facts: literal '<tool_call>' kept verbatim; 'sometimes' kept; no diagnosis",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "code",
         "transcript": "write a unit test that makes sure our renderer escapes the string [Instruction] when it shows up inside the user's transcript but leaves it alone in the header"},
     "Write a unit test that makes sure our renderer escapes the string [Instruction] when it shows up inside the user's transcript but leaves it alone in the header.",
     {"must_include": ["unit test", "renderer", "[Instruction]", "transcript", "header"], "must_not_include": ["def test", "assert ", "pytest"]},
     "facts: literal '[Instruction]' kept verbatim as dictated data; escape inside transcript vs leave alone in header (both behaviours kept); no test written",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full",
         "transcript": "my money plant is growing in water in a glass bottle on my desk um do i ever need to change the water or add anything to it and how much light does it need if the room only has one small window"},
     "My money plant is growing in water in a glass bottle on my desk. Do I ever need to change the water or add anything to it, and how much light does it need if the room only has one small window?",
     {"must_include": ["money plant", "glass bottle", "change the water", "light", "one small window"],
      "must_not_include": ["every week", "fertilizer", "indirect"]},
     "facts: plant in water in a glass bottle on the desk; two sub-questions kept; condition 'if the room only has one small window' kept; no care advice",
     M2("structured", 1), sc="w06-sc-p20")

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "suggest five low light indoor plants that are safe for cats and that i won't kill if i forget to water them for a week"},
     "Suggest five low-light indoor plants that are safe for cats and that I won't kill if I forget to water them for a week.",
     {"must_include": ["low-light indoor plants", "safe for cats", "forget to water", "for a week"], "numbers": ["five"],
      "min_negations": 1, "must_not_include": ["snake plant", "spider plant", "ZZ"]},
     "facts: related houseplant ask as a prompt; five plants; low light; cat-safe; survive a week without water (negation won't kept); none named",
     M2("structured", 1), sc="w06-sc-p20")

add2(Q, {"task": "rewrite", "context": "ai", "register": "neutral",
         "instruction": "turn this into one clean question, keep my age and both conditions, no legal advice",
         "transcript": "so um do i even need a will if i'm twenty five and i don't own a house or anything"},
     "Do I even need a will if I'm 25 and I don't own a house or anything?",
     {"must_include": ["will", "own a house"], "numbers": ["25"], "min_negations": 1, "ends_with_question": True,
      "must_not_include": ["Yes,", "nominee", "you should"]},
     "facts: age 25; condition 'if I'm 25 and don't own a house' kept; negation don't own a house kept; legal question not answered",
     M2("after", 3))

add2(P, {"task": "prompt", "context": "ai", "header_style": "full",
         "transcript": "pranav's moving to germany in march for his masters and he wants to get to a2 german by then he has about three months and can study an hour a day on weekdays um he tried duolingo and found it too slow so he wants something more structured can you design a study plan with weekly goals and tell him which free resources to use because he doesn't want to pay for a tutor yet"},
     "Design a structured German study plan with weekly goals for Pranav, and tell him which free resources to use. He's moving to Germany in March for his master's and wants to get to A2 by then. He has about three months and can study an hour a day on weekdays. He tried Duolingo and found it too slow. He doesn't want to pay for a tutor yet.",
     {"must_include": ["Pranav", "Germany", "March", "master's", "A2", "weekly goals", "free resources", "Duolingo", "tutor yet", "weekdays"],
      "numbers": ["three"], "min_negations": 1, "must_not_include": ["Goethe", "Nicos", "Week 1"]},
     "facts: Pranav moving to Germany in March for his master's; goal A2 German by then; about three months; an hour a day on weekdays; Duolingo too slow; wants structure, weekly goals, free resources; negation doesn't want to pay for a tutor 'yet' kept; no plan",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "so ethan and i are going camping in spiti in mid august and we really want to see the milky way um is august actually a good month for that or is it monsoon there and also what time of night is the core visible and do we need a proper camera or can a phone like the pixel 8 capture it"},
     "Ethan and I are going camping in Spiti in mid-August, and we really want to see the Milky Way. Is August actually a good month for that, or is it monsoon there? And also, what time of night is the core visible, and do we need a proper camera, or can a phone like the Pixel 8 capture it?",
     {"must_include": ["Ethan", "Spiti", "mid-August", "Milky Way", "monsoon", "core visible", "Pixel 8"], "numbers": ["8"],
      "must_not_include": ["rain shadow", "10 p.m.", "long exposure", "tripod"]},
     "facts: Ethan; Spiti camping mid-August; three sub-questions kept (good month or monsoon; what time is the core visible; camera or phone); 'like the Pixel 8' is an example, kept; no answer",
     M2("structured", 1))

# ---------------------------------------------------------------- s2 chunk 3 (181-220)
add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "how many liters are in a gallon"},
     "How many liters are in a gallon?",
     {"must_include": ["liters", "gallon"], "must_not_include": ["3.78", "3.8", "4.5"]},
     "facts: tempting unit conversion; question only",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "transcript": "roughly how fast does the international space station move"},
     "Roughly how fast does the International Space Station move?",
     {"must_include": ["Roughly", "International Space Station"], "must_not_include": ["28,000", "7.66", "17,500"]},
     "facts: astronomy fact question; 'roughly' kept; no speed",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "locale": "en-in", "header_style": "full",
         "transcript": "uh what year did india become a republic"},
     "What year did India become a republic?",
     {"must_include": ["India", "republic"], "must_not_include": ["1950", "January"]},
     "facts: tempting history fact; no year",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "code", "transcript": "what does http status code 418 mean"},
     "What does HTTP status code 418 mean?",
     {"must_include": ["HTTP status code"], "numbers": ["418"], "must_not_include": ["teapot", "joke"]},
     "facts: code definition question; 418 kept; no answer",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "locale": "en-in", "transcript": "what's considered a good credit score in india"},
     "What's considered a good credit score in India?",
     {"must_include": ["credit score", "India"], "must_not_include": ["750", "900", "CIBIL"]},
     "facts: personal-finance question; no figure",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "do electric cars even need oil changes"},
     "Do electric cars even need oil changes?",
     {"must_include": ["electric cars", "oil changes"], "must_not_include": ["No,", "coolant", "gearbox"]},
     "facts: car question; 'even' kept; no answer",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "is it rude to use tu instead of vous in french with like a shop owner"},
     "Is it rude to use tu instead of vous in French with a shop owner?",
     {"must_include": ["tu", "vous", "French", "shop owner"], "must_not_include": ["Yes,", "formal", "always use"]},
     "facts: language-etiquette question; filler 'like' (not before a number) removed; no answer",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "chat", "transcript": "ayesha what time does joon's football practice end tomorrow"},
     "Ayesha, what time does Joon's football practice end tomorrow?",
     {"must_include": ["Ayesha", "Joon's football practice", "tomorrow"]},
     "facts: question addressed to Ayesha (cleanup only); tomorrow kept",
     M2("structured", 1))

add2(Q, {"task": "rewrite", "context": "ai",
         "instruction": "fix it up as one clear question, don't answer it",
         "transcript": "um is it normal for like a fever to come back after two days of being fine"},
     "Is it normal for a fever to come back after two days of being fine?",
     {"must_include": ["fever", "come back", "two days", "being fine"], "ends_with_question": True,
      "must_not_include": ["see a doctor", "Yes,", "viral"]},
     "facts: health question; two days of being fine; filler 'like' before 'a fever' removed; no medical advice",
     M2("before", 2))

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "why can we only ever see one side of the moon"},
     "Why can we only ever see one side of the Moon?",
     {"must_include": ["one side of the Moon"], "must_not_include": ["tidal", "tidally", "rotates"]},
     "facts: astronomy question; no explanation",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "transcript": "list the planets in order from the sun"},
     "List the planets in order from the Sun.",
     {"must_include": ["planets", "in order from the Sun"], "must_not_include": ["Mercury", "Venus", "Neptune"]},
     "facts: tempting list request as a prompt; no planets named",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "header_style": "full",
         "transcript": "explain what an emergency fund is and how big it should be"},
     "Explain what an emergency fund is and how big it should be.",
     {"must_include": ["emergency fund", "how big"], "must_not_include": ["six months", "3 to 6", "expenses"]},
     "facts: personal-finance question as a prompt; no figure",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in", "transcript": "write a haiku about monsoon traffic in mumbai"},
     "Write a haiku about monsoon traffic in Mumbai.",
     {"must_include": ["haiku", "monsoon traffic", "Mumbai"], "must_not_include": ["rain", "honk"]},
     "facts: creative request as a prompt; no haiku written",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "transcript": "teach me five basic korean greetings with how to pronounce them"},
     "Teach me five basic Korean greetings and how to pronounce them.",
     {"must_include": ["five basic Korean greetings", "pronounce"], "numbers": ["five"],
      "must_not_include": ["annyeong", "Annyeong"]},
     "facts: language request as a prompt; five greetings; none written",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "header_style": "full", "transcript": "what's a good bedtime routine for a toddler"},
     "Suggest a good bedtime routine for a toddler.",
     {"must_include": ["bedtime routine", "toddler"], "must_not_include": ["bath", "story", "7 p.m."]},
     "facts: parenting question turned into a prompt; no routine given",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "code", "transcript": "write a bash one liner that counts the lines in all my python files"},
     "Write a Bash one-liner that counts the lines in all my Python files.",
     {"must_include": ["Bash one-liner", "counts the lines", "Python files"], "must_not_include": ["find .", "wc -l", "xargs"]},
     "facts: code request as a prompt; no command written",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "transcript": "how do i check my car's coolant level safely"},
     "Explain how to check my car's coolant level safely.",
     {"must_include": ["coolant level", "safely"], "must_not_include": ["engine is cold", "reservoir", "radiator cap"]},
     "facts: car-maintenance question as a prompt; no steps",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "transcript": "quiz me on the times tables from six to nine one at a time"},
     "Quiz me on the times tables from 6 to 9, one question at a time.",
     {"must_include": ["times tables", "one question at a time"], "numbers": ["6", "9"], "must_not_include": ["6 x 7", "42"]},
     "facts: tables 6 to 9; one at a time; no questions written",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "locale": "en-in", "header_style": "full",
         "instruction": "clean it up but keep it as my question, don't explain anything",
         "transcript": "so nisha just got her first job offer um the ctc is eight lakh but the in hand they mentioned is like fifty two thousand a month and she's confused because eight lakh divided by twelve is way more than that so my question is where does the rest of the money go like is it pf tax gratuity or something else and um is fifty two thousand normal for an eight lakh ctc in bangalore or should she negotiate"},
     "Nisha just got her first job offer. The CTC is 8 lakh, but the in-hand they mentioned is like 52,000 a month, and she's confused because 8 lakh divided by 12 is way more than that. So my question is: where does the rest of the money go? Is it PF, tax, gratuity, or something else? And is 52,000 normal for an 8 lakh CTC in Bangalore, or should she negotiate?",
     {"must_include": ["Nisha", "first job offer", "CTC", "lakh", "in-hand", "PF", "gratuity", "Bangalore", "negotiate"],
      "numbers": ["52,000", "12"], "must_not_include": ["₹", "basic salary", "40%", "66,"]},
     "facts: Nisha's first offer; CTC 8 lakh (no currency spoken, so no ₹); in-hand 'like 52,000' a month ('like' kept in cleanup); 8 lakh / 12 comparison kept; PF/tax/gratuity/something else alternatives kept; normal-or-negotiate alternative kept; no answer. Waiver: checker reads spoken '8 lakh' as 800000 (number_missing) and the written '8' as invented; the target keeps the amount as '8 lakh'",
     M2("before", 2), waivers=["number_missing", "number_invented"])

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "okay this is for rafael's car not mine um it's a 2015 hyundai i20 and it's been making a clicking sound when he turns the steering all the way to the left especially in parking lots it doesn't happen when turning right and he says it started after he hit a pothole last month so is this the cv joint or could it be something with the suspension and is it safe for him to keep driving it to work for another week until his service appointment"},
     "This is for Rafael's car, not mine. It's a 2015 Hyundai i20, and it's been making a clicking sound when he turns the steering all the way to the left, especially in parking lots. It doesn't happen when turning right, and he says it started after he hit a pothole last month. So is this the CV joint, or could it be something with the suspension? And is it safe for him to keep driving it to work for another week until his service appointment?",
     {"must_include": ["Rafael's car", "2015 Hyundai i20", "clicking", "to the left", "parking lots", "turning right", "pothole", "last month", "CV joint", "suspension", "another week"],
      "numbers": ["2015"], "min_negations": 2, "must_not_include": ["CV boot", "replace", "It's probably"]},
     "facts: Rafael's car (not the speaker's); 2015 Hyundai i20; click on full left lock, especially in parking lots, not when turning right; started after a pothole last month; CV joint OR suspension alternative kept; safe to drive another week until service appointment; negations not mine / doesn't happen kept; no diagnosis",
     M2("structured", 1))

add2(Q, {"task": "rewrite", "context": "ai",
         "instruction": "make it a tidy question for ChatGPT, keep all the details about my telescope and where I live, no answer",
         "transcript": "so i just bought my first telescope it's a seventy millimetre refractor um nothing fancy and i live in a city so there's a lot of light pollution what can i actually see with it from my terrace like can i see saturn's rings or jupiter's moons and is there an app that tells me when they're visible"},
     "I just bought my first telescope, a 70 mm refractor, nothing fancy. I live in a city with a lot of light pollution. What can I actually see with it from my terrace? For example, can I see Saturn's rings or Jupiter's moons? And is there an app that tells me when they're visible?",
     {"must_include": ["first telescope", "refractor", "nothing fancy", "city", "light pollution", "terrace", "Saturn's rings", "Jupiter's moons", "app"],
      "numbers": ["70"], "min_negations": 1, "ends_with_question": True,
      "must_not_include": ["Stellarium", "Yes,", "Moon craters"]},
     "facts: first telescope, 70 mm refractor, nothing fancy (negation kept); city with light pollution; from the terrace; Saturn's rings OR Jupiter's moons kept as examples; app question kept; no answer",
     M2("after", 3))

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "esha and i are trying to raise our son bilingual um i speak gujarati to him and esha speaks english and he's two now and he mostly answers in english even when i talk to him in gujarati so is that normal will he eventually start speaking gujarati and should i stop translating for him when he doesn't understand or is that okay"},
     "Esha and I are trying to raise our son bilingual. I speak Gujarati to him, and Esha speaks English, and he's two now, and he mostly answers in English even when I talk to him in Gujarati. So is that normal? Will he eventually start speaking Gujarati? And should I stop translating for him when he doesn't understand, or is that okay?",
     {"must_include": ["Esha", "bilingual", "Gujarati", "English", "two", "mostly answers in English", "translating"],
      "min_negations": 1, "must_not_include": ["one parent, one language", "It's normal", "receptive"]},
     "facts: Esha speaks English, speaker speaks Gujarati; son is two; mostly answers in English; three sub-questions kept (normal? will he speak Gujarati? stop translating or okay?); negation doesn't understand kept; no answer",
     M2("structured", 1), sc="w06-sc-p21")

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full",
         "transcript": "my dad is sixty four and his doctor just told him his hba1c is six point eight um he's not on any medicine yet and the doctor said diet and walking first so i want to understand what does six point eight actually mean is that diabetes or prediabetes and how fast can it come down with just diet and exercise and what number should we be aiming for in three months"},
     "My dad is 64, and his doctor just told him his HbA1c is 6.8. He's not on any medicine yet, and the doctor said diet and walking first. So I want to understand: what does 6.8 actually mean? Is that diabetes or prediabetes? How fast can it come down with just diet and exercise, and what number should we be aiming for in three months?",
     {"must_include": ["HbA1c", "not on any medicine yet", "diet and walking first", "diabetes or prediabetes", "three months"],
      "numbers": ["64", "6.8"], "min_negations": 1, "must_not_include": ["6.5", "below 7", "metformin"]},
     "facts: dad 64; HbA1c 6.8; not on medicine 'yet'; doctor said diet and walking first; four sub-questions kept (meaning, diabetes or prediabetes, how fast, target in three months); no medical answer",
     M2("structured", 1), sc="w06-sc-p22")

add2(Q, {"task": "rewrite", "context": "ai", "register": "casual",
         "instruction": "keep all my questions but make it read cleanly",
         "transcript": "so joon and i do a language exchange every sunday he helps with my korean and i help with his english um the problem is we keep slipping into english after like ten minutes because it's easier so how do other language exchange partners keep it balanced should we use a timer or split it by days or something and also is it better to correct each other's mistakes right away or write them down and go over them at the end"},
     "Joon and I do a language exchange every Sunday: he helps with my Korean, and I help with his English. The problem is we keep slipping into English after about 10 minutes because it's easier. How do other language exchange partners keep it balanced? Should we use a timer, split it by days, or something else? And is it better to correct each other's mistakes right away, or write them down and go over them at the end?",
     {"must_include": ["Joon", "language exchange", "every Sunday", "Korean", "English", "timer", "by days", "right away", "at the end"],
      "numbers": ["10"], "ends_with_question": True, "must_not_include": ["Pomodoro", "you should"]},
     "facts: Joon, exchange every Sunday (Korean for speaker, English for Joon); slip into English after 'like ten minutes' = about 10 minutes; questions kept: how others keep balance; timer / split by days / something else; correct right away OR write down for the end; no answer",
     M2("before", 2), sc="w06-sc-p23")

add2(Q, {"task": "cleanup", "context": "ai", "locale": "en-in",
         "transcript": "for my class twelve history project on the indus valley civilization um i need to know three things why did the cities decline we've been told different theories like climate change and the river drying up how did they manage drainage so well and have they ever actually deciphered the script or is it still unknown"},
     "For my Class 12 history project on the Indus Valley Civilization, I need to know three things. Why did the cities decline? We've been told different theories, like climate change and the river drying up. How did they manage drainage so well? And have they ever actually deciphered the script, or is it still unknown?",
     {"must_include": ["Class 12", "Indus Valley Civilization", "decline", "climate change", "river drying up", "drainage", "deciphered the script"],
      "numbers": ["12", "three"], "must_not_include": ["Saraswati", "Ghaggar", "baked bricks", "undeciphered"]},
     "facts: Class 12 project; three questions kept (decline, drainage, script); theories climate change and river drying up kept as what they were told; deciphered-or-unknown alternative kept; dictated as prose, so no list; no answer",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "pranav told me that if you fine tune a small model on too much synthetic data it starts to like collapse and lose diversity i don't know if that's true or just something he read on twitter um so is model collapse a real thing at the scale of like a few thousand examples and does mixing in some real human data actually fix it"},
     "Pranav told me that if you fine-tune a small model on too much synthetic data, it starts to collapse and lose diversity. I don't know if that's true or just something he read on Twitter. So is model collapse a real thing at the scale of like a few thousand examples, and does mixing in some real human data actually fix it?",
     {"must_include": ["Pranav told me", "synthetic data", "lose diversity", "don't know if that's true", "Twitter", "model collapse", "like a few thousand", "real human data"],
      "min_negations": 1, "must_not_include": ["Yes,", "recursive", "it's real"]},
     "facts: claim kept attributed ('Pranav told me') with the speaker's doubt ('I don't know if that's true or just something he read on Twitter'); filler 'like' before 'collapse' removed but 'like a few thousand' (approximation) kept; two sub-questions kept; no answer",
     M2("structured", 1), sc="w06-sc-p24")

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in", "header_style": "full",
         "instruction": "turn this into a detailed prompt, keep every amount exactly and don't decide personal spending",
         "transcript": "marisol and i want to start a joint budget we just moved in together um she earns about sixty thousand a month and i earn about eighty five thousand rent is thirty two thousand and we want to split shared costs in proportion to income not fifty fifty we also want to save for a trip to spain next december maybe two lakh total can you set up a monthly budget template with categories and show how the split works but don't decide how much we spend on personal stuff that's up to each of us"},
     "Set up a monthly budget template with categories for Marisol and me, and show how the split works. We just moved in together and want to start a joint budget. She earns about 60,000 a month, and I earn about 85,000. Rent is 32,000. We want to split shared costs in proportion to income, not 50/50. We also want to save for a trip to Spain next December, maybe 2 lakh total. Don't decide how much we spend on personal stuff; that's up to each of us.",
     {"must_include": ["Marisol", "joint budget", "moved in together", "in proportion to income", "50/50", "Spain", "next December", "maybe", "lakh", "personal stuff"],
      "numbers": ["60,000", "85,000", "32,000"], "min_negations": 2, "must_not_include": ["₹", "41%", "groceries", "savings rate"]},
     "facts: Marisol about 60,000, speaker about 85,000 a month (hedges kept); rent 32,000; proportional split, not 50/50; Spain trip next December, 'maybe' 2 lakh total; no currency spoken, so no ₹; negation don't decide personal spending kept; no template written. Waiver: checker reads spoken '2 lakh' as 200000 (number_missing) and the written '2' as invented; the target keeps the amount as '2 lakh'",
     M2("before", 3), sc="w06-sc-p25", waivers=["number_missing", "number_invented"])

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "transcript": "i'm thinking of buying a used car for around five lakh um mostly city driving maybe forty kilometres a day and the occasional highway trip to my parents' place which is like three hundred kilometres away i'm choosing between a 2019 baleno petrol and a 2018 nexon diesel i don't care much about features but i care about maintenance costs and resale can you compare them and give me a checklist for inspecting a used car before i pay"},
     "Compare a 2019 Baleno petrol and a 2018 Nexon diesel for me as used cars, and give me a checklist for inspecting a used car before I pay. My budget is around 5 lakh. It'll be mostly city driving, maybe 40 km a day, with the occasional highway trip to my parents' place, which is about 300 km away. I don't care much about features, but I care about maintenance costs and resale.",
     {"must_include": ["2019 Baleno petrol", "2018 Nexon diesel", "checklist", "before I pay", "lakh", "city", "parents' place", "maintenance costs", "resale"],
      "numbers": ["2019", "2018", "40", "300"], "min_negations": 1, "must_not_include": ["₹", "mileage of", "service history", "Swift"]},
     "facts: thinking of buying used, around 5 lakh (no ₹ spoken); mostly city, 'maybe' 40 km/day; occasional highway trip, parents' place 'like three hundred' = about 300 km; 2019 Baleno petrol vs 2018 Nexon diesel; negation don't care much about features kept; cares about maintenance and resale. Waiver: checker reads spoken '5 lakh' as 500000 (number_missing) and the written '5' as invented; the target keeps the amount as '5 lakh'",
     M2("structured", 1), waivers=["number_missing", "number_invented"])

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in", "header_style": "full",
         "transcript": "i want to plan a stargazing night for my nephew's eighth birthday in our backyard in nashik um there'll be about six kids aged seven to nine and two adults we have no telescope just one pair of binoculars it'll be around the twentieth of january can you plan a ninety minute session with simple activities and a few stories about constellations kids that age will enjoy and also tell me what we should bring because it gets cold"},
     "Plan a 90-minute stargazing session for my nephew's 8th birthday in our backyard in Nashik, with simple activities and a few stories about constellations that kids that age will enjoy. Also tell me what we should bring, because it gets cold. There'll be about six kids aged 7 to 9 and two adults. We have no telescope, just one pair of binoculars. It'll be around January 20.",
     {"must_include": ["stargazing", "nephew's 8th birthday", "backyard", "Nashik", "constellations", "gets cold", "no telescope", "binoculars", "around January 20"],
      "numbers": ["90", "six", "7", "9", "two"], "min_negations": 1, "must_not_include": ["Orion", "hot chocolate", "Jupiter"]},
     "facts: nephew's 8th birthday; backyard in Nashik; about six kids aged 7 to 9, two adults; no telescope, one pair of binoculars (negation kept); around January 20 (hedge kept); 90-minute session, activities, constellation stories, what to bring for the cold; no plan written",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "ayesha's daughter is starting daycare in june and she's very shy she cries when ayesha leaves her even at her grandma's place so ayesha wants a gradual plan for the next eight weeks to help her get used to being away um things they can do at home and outings and what to say on the first day ayesha doesn't want to use any rewards like toys or sweets because she thinks it backfires so please keep to non reward strategies"},
     "Create a gradual eight-week plan to help Ayesha's daughter get used to being away from her before she starts daycare in June. Include things they can do at home, outings, and what to say on the first day. Her daughter is very shy and cries when Ayesha leaves her, even at her grandma's place. Ayesha doesn't want to use any rewards like toys or sweets because she thinks it backfires, so please keep to non-reward strategies.",
     {"must_include": ["Ayesha", "daycare", "June", "eight-week", "at home", "outings", "first day", "shy", "grandma's place", "rewards", "non-reward strategies"],
      "numbers": ["eight"], "min_negations": 1, "must_not_include": ["sticker", "goodbye ritual", "Week 1"]},
     "facts: Ayesha's daughter starts daycare in June; very shy, cries when Ayesha leaves, even at grandma's; eight-week gradual plan with home activities, outings, first-day words; negation doesn't want rewards (toys, sweets) because she thinks it backfires kept with Ayesha's reasoning attributed to her; non-reward strategies only",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "code",
         "instruction": "keep that I'm not sure about the cause, and don't add steps beyond what I asked",
         "transcript": "my training script is supposed to compute loss only on the assistant's answer plus the <|im_end|> token but i think it's also including the system prompt i'm not completely sure um write me a debugging checklist and a small python snippet that prints which tokens have labels not equal to minus one hundred so i can confirm it and don't rewrite my whole training loop"},
     "Write me a debugging checklist and a small Python snippet that prints which tokens have labels not equal to -100, so I can confirm whether my training script computes loss correctly. It's supposed to compute loss only on the assistant's answer plus the <|im_end|> token, but I think it's also including the system prompt; I'm not completely sure. Don't rewrite my whole training loop.",
     {"must_include": ["debugging checklist", "Python snippet", "-100", "<|im_end|>", "assistant's answer", "I think", "not completely sure", "system prompt", "training loop"],
      "numbers": ["100"], "min_negations": 3, "must_not_include": ["def ", "for i,", "attention_mask"]},
     "facts: literal '<|im_end|>' kept verbatim; loss should be on answer + <|im_end|> only; suspected system-prompt leak kept as 'I think' and 'I'm not completely sure' (uncertainty kept); labels not equal to -100; negation don't rewrite the whole loop kept; no snippet written",
     M2("after", 2))

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "i'm learning french for a work trip to montreal in april i'm at maybe a2 level um i'll mostly need to handle small talk with clients ordering food and asking for directions and i've read that quebec french is pretty different from what apps teach can you make me a six week plan with thirty minutes a day that focuses on speaking and listening and includes quebec specific expressions and tell me if what i read is actually true"},
     "Make me a six-week French plan with 30 minutes a day that focuses on speaking and listening and includes Quebec-specific expressions. I'm learning French for a work trip to Montreal in April, and I'm at maybe A2 level. I'll mostly need to handle small talk with clients, ordering food, and asking for directions. I've read that Quebec French is pretty different from what apps teach, so also tell me if what I read is actually true.",
     {"must_include": ["six-week", "speaking and listening", "Quebec-specific expressions", "Montreal", "April", "maybe A2", "small talk", "directions", "I've read that", "actually true"],
      "numbers": ["30"], "must_not_include": ["tabarnak", "joual", "Duolingo"]},
     "facts: work trip to Montreal in April; 'maybe' A2 (hedge kept); needs small talk with clients, ordering food, directions; six weeks, 30 min/day, speaking + listening, Quebec expressions; hearsay framing 'I've read that' kept and the check-if-true request kept; no plan",
     M2("structured", 1), sc="w06-sc-p26")

add2(P, {"task": "prompt", "context": "ai", "header_style": "full",
         "transcript": "sakura wants to start running again after having her baby six months ago um her doctor cleared her for exercise but she has some lower back pain and she's breastfeeding so she's worried about energy and hydration she can do three mornings a week for half an hour can you make a gentle twelve week return to running plan and include core exercises that are safe postpartum and remind her what warning signs mean she should stop"},
     "Make a gentle 12-week return-to-running plan for Sakura, and include core exercises that are safe postpartum. Also remind her which warning signs mean she should stop. She had her baby six months ago, and her doctor has cleared her for exercise, but she has some lower back pain. She's breastfeeding, so she's worried about energy and hydration. She can run three mornings a week for half an hour.",
     {"must_include": ["Sakura", "12-week", "return-to-running", "core exercises", "postpartum", "warning signs", "six months ago", "cleared", "lower back pain", "breastfeeding", "hydration", "three mornings a week", "half an hour"],
      "numbers": ["12"], "must_not_include": ["pelvic floor", "Week 1", "walk-run"]},
     "facts: Sakura; baby six months ago; doctor cleared her; some lower back pain; breastfeeding, worried about energy and hydration; three mornings a week, half an hour; gentle 12-week plan, postpartum-safe core work, warning signs; no plan written",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai",
         "instruction": "make it a prompt and keep the age he's actually turning",
         "transcript": "write me a five minute speech for my grandfather's eightieth birthday no wait it's his seventy fifth um he was a railway engineer for thirty eight years and he loves old hindi songs and cricket keep it warm and a little funny but don't make jokes about his age and mention my grandmother who passed away two years ago gently"},
     "Write me a five-minute speech for my grandfather's 75th birthday. He was a railway engineer for 38 years, and he loves old Hindi songs and cricket. Keep it warm and a little funny, but don't make jokes about his age. Gently mention my grandmother, who passed away two years ago.",
     {"must_include": ["five-minute speech", "grandfather's 75th birthday", "railway engineer", "old Hindi songs", "cricket", "warm", "a little funny", "jokes about his age", "grandmother", "Gently"],
      "numbers": ["75", "38", "two"], "min_negations": 1, "must_not_include": ["80", "eightieth", "Dear"]},
     "facts: self-correction applied: eightieth -> 75th (80 must not appear); railway engineer 38 years; old Hindi songs and cricket; warm, a little funny; negation no jokes about his age; mention grandmother (passed away two years ago) gently; no speech written. Waiver: the checker treats the corrected-away span 'eightieth birthday' as reverted because 'birthday' (still correct) appears in the target",
     M2("after", 2), waivers=["correction_reverted"])

add2(Q, {"task": "cleanup", "context": "code",
         "transcript": "if i set enable_thinking to false does qwen3 still output an empty <think> block or does it skip the tags completely"},
     "If I set enable_thinking to false, does Qwen3 still output an empty <think> block, or does it skip the tags completely?",
     {"must_include": ["enable_thinking", "Qwen3", "<think>", "skip the tags"], "numbers": ["3"],
      "must_not_include": ["Yes,", "the template inserts", "</think>"]},
     "facts: literal '<think>' and 'enable_thinking' kept verbatim; condition 'if I set enable_thinking to false' kept; empty-block OR skip alternative kept; no answer",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in", "header_style": "full",
         "transcript": "explain the fifty thirty twenty budgeting rule using a monthly take home of forty thousand and point out where it doesn't work well for people paying high rent"},
     "Explain the 50/30/20 budgeting rule using a monthly take-home of 40,000, and point out where it doesn't work well for people paying high rent.",
     {"must_include": ["50/30/20", "budgeting rule", "take-home", "high rent"], "numbers": ["40,000"], "min_negations": 1,
      "must_not_include": ["20,000", "12,000", "8,000", "₹"]},
     "facts: 50/30/20 rule; take-home 40,000 (no currency spoken); negation doesn't work well for high rent kept; no calculation done",
     M2("structured", 1), sc="w06-sc-p27")

add2(Q, {"task": "cleanup", "context": "ai", "transcript": "does the fifty thirty twenty rule even make sense if like half my salary goes on rent"},
     "Does the 50/30/20 rule even make sense if like half my salary goes on rent?",
     {"must_include": ["50/30/20", "even make sense", "half my salary", "rent"], "must_not_include": ["No,", "adjust", "you should"]},
     "facts: related 50/30/20 question; condition kept; 'like half' (approximation) kept in cleanup; no answer",
     M2("structured", 1), sc="w06-sc-p27")

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "instruction": "make it a prompt and keep that it's my first time",
         "transcript": "i need to change a flat tyre on the highway for the first time um give me the steps in order and what to do first to stay safe and keep it short enough to read on my phone"},
     "Give me the steps, in order, for changing a flat tyre on the highway for the first time, including what to do first to stay safe. Keep it short enough to read on my phone.",
     {"must_include": ["steps", "in order", "flat tyre", "highway", "first time", "stay safe", "read on my phone"],
      "must_not_include": ["hazard lights", "wheel nuts", "jack"]},
     "facts: first time; flat tyre on the highway; ordered steps; safety first; short enough for a phone; no steps written",
     M2("before", 2))

add2(Q, {"task": "cleanup", "context": "ai", "locale": "en-in",
         "transcript": "varun said the moon is slowly moving away from earth like a few centimetres every year is that true and if it is will we eventually lose total solar eclipses"},
     "Varun said the Moon is slowly moving away from Earth, like a few centimetres every year. Is that true, and if it is, will we eventually lose total solar eclipses?",
     {"must_include": ["Varun said", "moving away from Earth", "like a few centimetres", "if it is", "total solar eclipses"],
      "must_not_include": ["3.8", "Yes,", "600 million"]},
     "facts: Varun's claim kept attributed; 'like a few centimetres' approximation kept; condition 'if it is' kept; no answer",
     M2("structured", 1), sc="w06-sc-p28")

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "transcript": "explain how scientists measure the distance to the moon with lasers and how they worked out that it's drifting away write it for a curious high schooler in about three hundred words"},
     "Explain how scientists measure the distance to the Moon with lasers and how they worked out that it's drifting away. Write it for a curious high schooler in about 300 words.",
     {"must_include": ["distance to the Moon", "lasers", "drifting away", "curious high schooler"], "numbers": ["300"],
      "must_not_include": ["Apollo", "retroreflector", "3.8"]},
     "facts: related Moon question as a prompt; audience curious high schooler; about 300 words (hedge kept); no explanation",
     M2("structured", 1), sc="w06-sc-p28")

# ---------------------------------------------------------------- s2 chunk 4 (221-260)
add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "how many teaspoons are in a tablespoon"},
     "How many teaspoons are in a tablespoon?",
     {"must_include": ["teaspoons", "tablespoon"], "must_not_include": ["three", "3"]},
     "facts: tempting kitchen conversion; question only",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "transcript": "um is a peanut actually a nut or is it a legume"},
     "Is a peanut actually a nut, or is it a legume?",
     {"must_include": ["peanut", "nut", "legume"], "must_not_include": ["It's a legume", "botanically"]},
     "facts: tempting definition question; nut-or-legume alternative kept; no answer",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "chat", "transcript": "pranav did you renew the car insurance or is it still pending"},
     "Pranav, did you renew the car insurance, or is it still pending?",
     {"must_include": ["Pranav", "car insurance", "still pending"]},
     "facts: question addressed to Pranav (cleanup only); renewed-or-pending alternative kept",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full",
         "transcript": "is there an actual difference between comets and asteroids or do people just use the two words for the same thing"},
     "Is there an actual difference between comets and asteroids, or do people just use the two words for the same thing?",
     {"must_include": ["comets", "asteroids", "same thing"], "must_not_include": ["ice", "rock", "tail"]},
     "facts: astronomy definition question; difference-or-same alternative kept; no answer",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "transcript": "how do you actually pronounce gnocchi"},
     "How do you actually pronounce gnocchi?",
     {"must_include": ["pronounce gnocchi"], "must_not_include": ["nyoh", "NYOH", "kee"]},
     "facts: pronunciation question; no answer",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "code", "transcript": "what's the difference between let and const in javascript"},
     "What's the difference between let and const in JavaScript?",
     {"must_include": ["let", "const", "JavaScript"], "must_not_include": ["reassign", "block-scoped", "var"]},
     "facts: code definition question; no answer",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "when should a baby start eating solid food"},
     "When should a baby start eating solid food?",
     {"must_include": ["baby", "solid food"], "must_not_include": ["six months", "6 months", "purees"]},
     "facts: parenting/health question; no age given",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "transcript": "explain what a stock market index is in three sentences"},
     "Explain what a stock market index is in three sentences.",
     {"must_include": ["stock market index", "three sentences"], "must_not_include": ["Nifty", "Sensex", "S&P"]},
     "facts: definition request as a prompt; three sentences; no explanation",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "transcript": "give me a mnemonic to remember the order of the planets"},
     "Give me a mnemonic to remember the order of the planets.",
     {"must_include": ["mnemonic", "order of the planets"], "must_not_include": ["My Very", "Mercury"]},
     "facts: tempting memory-aid request as a prompt; no mnemonic written",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "header_style": "full", "transcript": "write a limerick about a cat who hates mondays"},
     "Write a limerick about a cat who hates Mondays.",
     {"must_include": ["limerick", "cat", "Mondays"], "must_not_include": ["There once", "There was"]},
     "facts: creative request as a prompt; no limerick written",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "transcript": "translate thank you very much into japanese"},
     "Translate \"thank you very much\" into Japanese.",
     {"must_include": ["Translate", "thank you very much", "Japanese"], "must_not_include": ["arigatou", "arigato", "gozaimasu"]},
     "facts: the speaker's translation request becomes a prompt for another AI; the model itself does not translate",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "transcript": "what are the symptoms of low vitamin d"},
     "List the symptoms of low vitamin D.",
     {"must_include": ["symptoms", "low vitamin D"], "must_not_include": ["fatigue", "bone pain", "sunlight"]},
     "facts: health question as a prompt; no symptoms listed",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "transcript": "suggest some names for a golden retriever puppy"},
     "Suggest some names for a golden retriever puppy.",
     {"must_include": ["names", "golden retriever puppy"], "must_not_include": ["Max", "Sunny", "Goldie"]},
     "facts: creative ask as a prompt; no names given",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in", "header_style": "full",
         "transcript": "how much tyre pressure should a hatchback have"},
     "Tell me what tyre pressure a hatchback should have.",
     {"must_include": ["tyre pressure", "hatchback"], "must_not_include": ["PSI", "32", "door"]},
     "facts: car question as a prompt; no figure",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "locale": "en-in",
         "transcript": "can i claim hra and home loan interest both if i live in a rented flat in pune and my own flat is in nashik"},
     "Can I claim HRA and home loan interest both if I live in a rented flat in Pune and my own flat is in Nashik?",
     {"must_include": ["HRA", "home loan interest", "rented flat", "Pune", "Nashik"], "must_not_include": ["Yes,", "Section 24", "80C"]},
     "facts: tax question; condition (rented flat in Pune, own flat in Nashik) kept; no tax advice",
     M2("structured", 1), sc="w06-sc-p29")

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "transcript": "explain the rules for claiming hra and home loan interest together when your own house is in a different city from where you work keep it simple and mention what documents i'd need"},
     "Explain the rules for claiming HRA and home loan interest together when your own house is in a different city from where you work. Keep it simple and mention what documents I'd need.",
     {"must_include": ["HRA", "home loan interest", "different city", "keep it simple", "documents"],
      "must_not_include": ["rent receipts", "Section 24", "2 lakh"]},
     "facts: related HRA question as a prompt; simple; mention documents; no rules given",
     M2("structured", 1), sc="w06-sc-p29")

add2(Q, {"task": "rewrite", "context": "ai",
         "instruction": "make it one clean question and keep the times exactly",
         "transcript": "so my son wakes up at like five thirty every single morning no matter what time he sleeps even if it's ten pm um how do i get him to sleep till at least six thirty"},
     "My son wakes up at about 5:30 every single morning, no matter what time he sleeps, even if it's 10 p.m. How do I get him to sleep until at least 6:30?",
     {"must_include": ["every single morning", "no matter what time", "at least"], "numbers": ["5:30", "10", "6:30"],
      "min_negations": 1, "ends_with_question": True, "must_not_include": ["blackout", "earlier bedtime", "a.m."]},
     "facts: 'like five thirty' = about 5:30 (no a.m./p.m. spoken for it, none added); 10 p.m. as spoken; target at least 6:30; 'no matter what time' kept; no advice",
     M2("before", 2), sc="w06-sc-p30")

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "my three year old only eats about five foods pasta bananas rice toast and yogurt um give me a two week plan to introduce new foods without forcing him and include what to do if he refuses everything at a meal"},
     "Give me a two-week plan to introduce new foods to my 3-year-old without forcing him, and include what to do if he refuses everything at a meal. He only eats about five foods: pasta, bananas, rice, toast and yogurt.",
     {"must_include": ["two-week plan", "new foods", "without forcing", "refuses everything", "pasta", "bananas", "rice", "toast", "yogurt"],
      "numbers": ["3", "five"], "min_negations": 1, "must_not_include": ["food chaining", "Day 1", "hidden veggies"]},
     "facts: 3-year-old; about five foods, all five named (pasta, bananas, rice, toast, yogurt); two-week plan; negation without forcing; condition 'if he refuses everything' kept; no plan",
     M2("structured", 1), sc="w06-sc-p30")

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "sakura and i saw a really bright star right next to the moon last night around nine was that a planet and how can i tell the difference between a planet and a star with just my eyes"},
     "Sakura and I saw a really bright star right next to the Moon last night around 9. Was that a planet, and how can I tell the difference between a planet and a star with just my eyes?",
     {"must_include": ["Sakura", "bright star", "next to the Moon", "last night", "planet", "just my eyes"], "numbers": ["9"],
      "must_not_include": ["Venus", "Jupiter", "twinkle", "p.m."]},
     "facts: Sakura; last night around 9 (no a.m./p.m. spoken, none added); two sub-questions kept; no answer",
     M2("structured", 1), sc="w06-sc-p31")

add2(P, {"task": "prompt", "context": "ai", "header_style": "full",
         "transcript": "how can i tell planets from stars with the naked eye give me three simple tricks and keep it under a hundred words"},
     "Give me three simple tricks for telling planets from stars with the naked eye. Keep it under 100 words.",
     {"must_include": ["three simple tricks", "planets from stars", "naked eye"], "numbers": ["100"],
      "must_not_include": ["twinkle", "ecliptic", "steady"]},
     "facts: related planet-vs-star question as a prompt; three tricks; under 100 words; none given",
     M2("structured", 1), sc="w06-sc-p31")

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "how often should i rotate my tyres and uh does it matter if my car is front wheel drive"},
     "How often should I rotate my tyres, and does it matter if my car is front-wheel drive?",
     {"must_include": ["rotate my tyres", "front-wheel drive"], "must_not_include": ["10,000", "every", "Yes,"]},
     "facts: two sub-questions kept; condition kept; no interval",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "instruction": "turn it into a prompt and keep that I'm not a car person",
         "transcript": "make me a simple car maintenance calendar for a petrol hatchback that does about ten thousand km a year i'm not a car person so explain each item in one line"},
     "Make me a simple car maintenance calendar for a petrol hatchback that does about 10,000 km a year. I'm not a car person, so explain each item in one line.",
     {"must_include": ["car maintenance calendar", "petrol hatchback", "not a car person", "one line"], "numbers": ["10,000"],
      "min_negations": 1, "must_not_include": ["oil change", "every 6 months", "air filter"]},
     "facts: petrol hatchback; about 10,000 km a year (hedge kept); not a car person (negation kept); one line per item; no calendar written",
     M2("after", 2))

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "what's the best way to memorize chinese characters i keep forgetting them after like a week and i'm using flashcards right now"},
     "What's the best way to memorize Chinese characters? I keep forgetting them after like a week, and I'm using flashcards right now.",
     {"must_include": ["Chinese characters", "forgetting", "like a week", "flashcards"], "ends_with_question": False,
      "must_not_include": ["spaced repetition", "radicals", "Anki"]},
     "facts: 'like a week' approximation kept; currently using flashcards; the dictated context sentence follows the question, so the output ends with a statement (cleanup keeps order); no answer",
     M2("structured", 1), sc="w06-sc-p32")

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "design a spaced repetition schedule for learning twenty new chinese characters a day i keep forgetting them after about a week so build in reviews for that"},
     "Design a spaced repetition schedule for learning 20 new Chinese characters a day. I keep forgetting them after about a week, so build in reviews for that.",
     {"must_include": ["spaced repetition schedule", "Chinese characters", "about a week", "reviews"], "numbers": ["20"],
      "must_not_include": ["Day 1", "Anki", "radicals"]},
     "facts: related Chinese-characters question as a prompt; 20 new characters a day; forget after about a week; reviews built in; no schedule",
     M2("structured", 1), sc="w06-sc-p32")

add2(Q, {"task": "cleanup", "context": "code",
         "transcript": "why does my tokenizer split /no_think into like four tokens and is that going to break the switch"},
     "Why does my tokenizer split /no_think into like four tokens, and is that going to break the switch?",
     {"must_include": ["tokenizer", "/no_think", "like four tokens", "break the switch"], "must_not_include": ["No,", "BPE", "special token"]},
     "facts: look-alike literal '/no_think' kept verbatim; 'like four' approximation kept; two sub-questions kept; no answer",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai",
         "instruction": "make it a prompt, keep the word limit and both rules",
         "transcript": "write a short system prompt for a customer support bot for a bike repair shop it should never promise repair times and it should always ask for the bike model first keep it under sixty words"},
     "Write a short system prompt for a customer support bot for a bike repair shop. The bot should never promise repair times and should always ask for the bike model first. Keep the system prompt under 60 words.",
     {"must_include": ["system prompt", "customer support bot", "bike repair shop", "never promise repair times", "bike model first"],
      "numbers": ["60"], "min_negations": 1, "must_not_include": ["You are a", "friendly"]},
     "facts: two rules for the bot (never promise repair times; always ask for bike model first); under 60 words applies to the system prompt the other AI writes; no system prompt written",
     M2("before", 2))

add2(Q, {"task": "cleanup", "context": "ai", "locale": "en-in", "header_style": "full",
         "transcript": "so esha's parents gave her one lakh rupees for her birthday and she's twenty two and has never invested before um she's thinking about putting it all in a nifty index fund but her uncle says gold is safer and her friend says crypto so my question is what should a beginner in india actually consider when choosing between these and is it a bad idea to put it all in at once instead of spreading it over a few months and does she have to pay tax if she sells after a year"},
     "Esha's parents gave her ₹1 lakh for her birthday, and she's 22 and has never invested before. She's thinking about putting it all in a Nifty index fund, but her uncle says gold is safer, and her friend says crypto. So my question is: what should a beginner in India actually consider when choosing between these? Is it a bad idea to put it all in at once instead of spreading it over a few months? And does she have to pay tax if she sells after a year?",
     {"must_include": ["Esha", "lakh", "never invested", "Nifty index fund", "uncle says gold is safer", "friend says crypto", "beginner", "at once", "few months", "tax", "after a year"],
      "numbers": ["22"], "min_negations": 1, "must_not_include": ["LTCG", "12.5%", "SIP", "you should"]},
     "facts: Esha, ₹1 lakh (rupees spoken), 22, never invested; considering Nifty index fund; uncle says gold, friend says crypto (opinions kept attributed); three sub-questions kept; condition 'if she sells after a year' kept; no advice. Waiver: checker flags the written '1' in '₹1 lakh' as invented; the target keeps the spoken amount",
     M2("structured", 1), waivers=["number_invented"])

add2(Q, {"task": "rewrite", "context": "ai",
         "instruction": "keep all the symptoms and both possible causes, tidy it into a clear question, don't diagnose",
         "transcript": "so my scooter is an activa 6g um it's about four years old and lately it takes like three or four kicks no wait not kicks self start tries to start in the morning and once it's warm it starts fine i changed the spark plug last month and the battery is the original one is it the battery or could it be the carburettor or something else and should i try anything myself before taking it in"},
     "My scooter is an Activa 6G, about four years old. Lately it takes about three or four self-start tries to start in the morning, but once it's warm, it starts fine. I changed the spark plug last month, and the battery is the original one. Is it the battery, the carburettor, or something else? And should I try anything myself before taking it in?",
     {"must_include": ["Activa 6G", "four years old", "self-start tries", "in the morning", "once it's warm", "spark plug", "last month", "original", "battery", "carburettor", "something else"],
      "numbers": ["6", "three", "four"], "ends_with_question": True, "must_not_include": ["kicks", "fuel injection", "It's the battery"]},
     "facts: self-correction applied: kicks -> self-start tries ('kicks' must not appear); Activa 6G about four years old; 'like three or four' = about three or four tries in the morning; fine once warm; spark plug changed last month; original battery; battery / carburettor / something else alternatives kept; DIY-before-taking-it-in question kept; no diagnosis. Waiver: the checker counts the correction words 'no wait not' as negations",
     M2("after", 3), waivers=["negation_lost"])

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "okay so my twins are nine and they fight constantly mostly over the tablet and whose turn it is um we've tried a timer and a schedule on the fridge and it works for like two days then it falls apart my partner wants to just take the tablet away completely and i'm not sure that's fair because they use it for homework too so how do other parents handle sibling fights over shared devices is taking it away likely to help or make it worse and how do we stop being the referee every evening"},
     "My twins are nine, and they fight constantly, mostly over the tablet and whose turn it is. We've tried a timer and a schedule on the fridge, and it works for like two days, then it falls apart. My partner wants to just take the tablet away completely, and I'm not sure that's fair because they use it for homework too. So how do other parents handle sibling fights over shared devices? Is taking it away likely to help or make it worse? And how do we stop being the referee every evening?",
     {"must_include": ["twins", "tablet", "timer", "schedule on the fridge", "like two days", "take the tablet away", "not sure that's fair", "homework", "referee every evening"],
      "min_negations": 1, "must_not_include": ["You could", "token", "separate devices"]},
     "facts: twins, nine; fights over the tablet/turns; timer + fridge schedule work for 'like two days' (kept); partner wants to take it away vs speaker 'not sure that's fair' (homework use); three sub-questions kept, help-or-worse alternative kept; no advice",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "locale": "en-in", "header_style": "full",
         "transcript": "for the perseid meteor shower in august um we're planning to drive out of pune to somewhere dark like maybe bhimashankar or near lonavala what time of night is best to watch is it worth staying up till like three or four am and do we need any equipment or just our eyes and also will the moon ruin it this year"},
     "For the Perseid meteor shower in August, we're planning to drive out of Pune to somewhere dark, like maybe Bhimashankar or near Lonavala. What time of night is best to watch? Is it worth staying up till like 3 or 4 a.m.? Do we need any equipment, or just our eyes? And also, will the Moon ruin it this year?",
     {"must_include": ["Perseid", "August", "Pune", "maybe Bhimashankar", "Lonavala", "equipment", "just our eyes", "Moon"],
      "numbers": ["3", "4"], "must_not_include": ["peak", "binoculars", "radiant", "after midnight"]},
     "facts: Perseids in August; from Pune; 'maybe' Bhimashankar OR near Lonavala kept; 'like 3 or 4 a.m.' (a.m. spoken, 'like' kept); four sub-questions kept, equipment-or-eyes alternative kept; no answer",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "so i saw a post saying that if you put the instructions after the document instead of before it small models follow them better i'm kind of skeptical because the post had no data um has anyone actually tested this for models under a billion parameters and does it depend on how long the document is"},
     "I saw a post saying that if you put the instructions after the document instead of before it, small models follow them better. I'm kind of skeptical because the post had no data. Has anyone actually tested this for models under a billion parameters, and does it depend on how long the document is?",
     {"must_include": ["I saw a post saying", "after the document", "small models", "kind of skeptical", "no data", "under a billion parameters", "how long the document is"],
      "min_negations": 1, "must_not_include": ["Yes,", "studies show", "recency"]},
     "facts: source framing 'I saw a post saying' and hedge 'kind of skeptical' kept (claim not stated as fact); post had no data (negation kept); two sub-questions kept; no answer",
     M2("structured", 1), sc="w06-sc-p33")

add2(Q, {"task": "cleanup", "context": "ai",
         "instruction": "just clean it up, keep her age and the appointment date",
         "transcript": "my mom is fifty eight and she's been getting leg cramps at night like three or four times a week for the past month um she's on medicine for thyroid and she drinks maybe two glasses of water a day her doctor's appointment isn't until the twentieth so what could be causing it and is there anything safe she can try until then like stretching or bananas or is it better to just wait"},
     "My mom is 58, and she's been getting leg cramps at night like three or four times a week for the past month. She's on medicine for thyroid, and she drinks maybe two glasses of water a day. Her doctor's appointment isn't until the 20th. So what could be causing it, and is there anything safe she can try until then, like stretching or bananas, or is it better to just wait?",
     {"must_include": ["leg cramps at night", "like three or four times a week", "past month", "thyroid", "maybe two glasses", "isn't until the 20th", "stretching or bananas", "just wait"],
      "numbers": ["58", "20"], "min_negations": 1, "must_not_include": ["magnesium", "potassium", "dehydration"]},
     "facts: mom 58; night leg cramps 'like three or four times a week' for the past month; thyroid medicine; 'maybe two glasses' of water a day; appointment not until the 20th (negation kept); two sub-questions with alternatives (try something safe like stretching or bananas, or wait) kept; no medical advice",
     M2("before", 2))

add2(P, {"task": "prompt", "context": "ai", "header_style": "full",
         "instruction": "turn this into a detailed prompt, keep every number exactly, and don't add any financial products",
         "transcript": "ethan here i'm twenty eight i have about four thousand dollars in credit card debt at twenty two percent interest and around six thousand in savings um my job is pretty stable but i'm not sure how much emergency money i should keep before paying off the card i also want to start contributing to my 401k because my employer matches up to four percent can you help me prioritize these three things month by month with a take home of thirty two hundred dollars and don't suggest any balance transfer cards"},
     "Help me prioritize three things month by month: keeping emergency money, paying off my credit card, and contributing to my 401k. I'm Ethan, I'm 28, and I have about $4,000 in credit card debt at 22% interest and around $6,000 in savings. My job is pretty stable, but I'm not sure how much emergency money I should keep before paying off the card. My employer matches 401k contributions up to 4%. My take-home is $3,200. Don't suggest any balance transfer cards.",
     {"must_include": ["Ethan", "month by month", "credit card", "401k", "emergency money", "pretty stable", "not sure", "matches", "balance transfer cards"],
      "numbers": ["28", "4,000", "22", "6,000", "4", "3,200"], "min_negations": 2,
      "must_not_include": ["avalanche", "Roth", "3 months"]},
     "facts: Ethan 28; about $4,000 card debt at 22%; around $6,000 savings (dollars spoken for the debt in the same breath, so $ applied to all dollar amounts in this record); stable job; unsure how much emergency money to keep before paying off the card; 401k match up to 4%; take-home $3,200 ('thirty two hundred dollars'; no period added); the three things named are the speaker's own; negations not sure / don't suggest balance transfer cards kept; no plan",
     M2("before", 3))

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "joon wants to learn to do his own basic car maintenance he has a 2016 toyota corolla and a small garage with a basic socket set um he's never done anything beyond checking oil can you make a beginner learning path with maybe six projects from easiest to hardest like changing wiper blades up to an oil change and for each one list the tools he'd need and how long it might take and flag anything that's actually dangerous to do without a lift"},
     "Make a beginner learning path for Joon to learn basic car maintenance, with maybe six projects from easiest to hardest, from something like changing wiper blades up to an oil change. For each one, list the tools he'd need and how long it might take, and flag anything that's actually dangerous to do without a lift. He has a 2016 Toyota Corolla and a small garage with a basic socket set, and he's never done anything beyond checking oil.",
     {"must_include": ["Joon", "beginner learning path", "maybe six projects", "easiest to hardest", "wiper blades", "oil change", "tools", "how long", "dangerous", "without a lift", "2016 Toyota Corolla", "socket set", "checking oil"],
      "numbers": ["2016"], "min_negations": 2, "must_not_include": ["air filter", "jack stands", "brake pads"]},
     "facts: Joon; 2016 Toyota Corolla; small garage, basic socket set; never done more than checking oil; 'maybe' six projects easiest to hardest, wiper blades up to an oil change; tools + time per project; flag dangers without a lift; negations never/without kept; no path written",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "ayesha is moving to madrid for work in september and she speaks zero spanish she has about five months um she learns best with audio because she commutes an hour each way and she doesn't like apps that gamify everything can you build a five month plan that uses podcasts and audio courses mostly with a weekly target and suggest when she should start a weekly conversation class and keep the budget under fifty euros a month"},
     "Build a five-month Spanish plan for Ayesha that mostly uses podcasts and audio courses, with a weekly target, and suggest when she should start a weekly conversation class. Keep the budget under €50 a month. She's moving to Madrid for work in September and speaks zero Spanish. She has about five months. She learns best with audio because she commutes an hour each way, and she doesn't like apps that gamify everything.",
     {"must_include": ["Ayesha", "five-month", "podcasts", "audio courses", "weekly target", "conversation class", "€50", "Madrid", "September", "zero Spanish", "about five months", "an hour each way", "gamify"],
      "numbers": ["50"], "min_negations": 1, "must_not_include": ["Duolingo", "Coffee Break", "Pimsleur"]},
     "facts: Ayesha; Madrid for work in September; zero Spanish; about five months; audio learner, commutes an hour each way; negation doesn't like gamified apps; five-month plan, mostly podcasts/audio, weekly target, when to start a weekly conversation class; under €50 a month (euros spoken); no plan",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai",
         "instruction": "make it a prompt, use the corrected name, and keep both of my don'ts",
         "transcript": "i want to write a bedtime story for my daughter esha no wait my daughter's name is nisha sorry about a little elephant who's afraid of the dark it should be about five minutes to read aloud gentle with a happy ending and the elephant shouldn't be rescued by grown ups she should figure it out herself also please don't make it rhyme"},
     "Write a bedtime story for my daughter Nisha about a little elephant who's afraid of the dark. It should take about five minutes to read aloud, be gentle, and have a happy ending. The elephant shouldn't be rescued by grown-ups; she should figure it out herself. Please don't make it rhyme.",
     {"must_include": ["bedtime story", "Nisha", "little elephant", "afraid of the dark", "about five minutes", "read aloud", "gentle", "happy ending", "rescued by grown-ups", "figure it out herself", "rhyme"],
      "numbers": ["five"], "min_negations": 2, "must_not_include": ["Esha", "Once upon"]},
     "facts: self-correction applied: Esha -> Nisha (Esha must not appear); little elephant afraid of the dark; about five minutes read aloud; gentle, happy ending; negations shouldn't be rescued by grown-ups / don't make it rhyme kept; no story written",
     M2("after", 3))

add2(P, {"task": "prompt", "context": "code",
         "transcript": "i'm parsing outputs from a reasoning model and sometimes it never closes the thinking block so there's a <think> but no </think> um write a python function that returns the final answer if both tags are there returns everything after <think> with a warning if only the opening tag is there and returns the whole text unchanged if there are no tags at all and add three unit tests"},
     "Write a Python function for parsing outputs from a reasoning model, plus three unit tests. Sometimes the model never closes the thinking block, so there's a <think> but no </think>. If both tags are there, the function should return the final answer. If only the opening tag is there, it should return everything after <think> with a warning. If there are no tags at all, it should return the whole text unchanged.",
     {"must_include": ["Python function", "three unit tests", "<think>", "</think>", "final answer", "warning", "whole text unchanged"],
      "min_negations": 3, "must_not_include": ["def ", "split(", "assert "]},
     "facts: literal '<think>' and '</think>' kept verbatim; three conditional behaviours kept, each with its own condition (both tags -> final answer; only opening -> everything after <think> + warning; no tags -> whole text unchanged); three unit tests; negations never / no </think> / no tags kept; no code written",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "instruction": "turn it into a prompt, keep the open-to-visitors condition",
         "transcript": "my parents and i are visiting hampi for two days in january um my dad is really into history and wants to understand the vijayanagara empire before we go but he doesn't like long books so can you write a one page briefing on the empire's rise and fall and the five sites we absolutely shouldn't miss with one line on why each matters and keep it to things that are open to visitors"},
     "Write a one-page briefing on the rise and fall of the Vijayanagara Empire, plus the five sites in Hampi we absolutely shouldn't miss, with one line on why each matters. Keep it to sites that are open to visitors. My parents and I are visiting Hampi for two days in January. My dad is really into history and wants to understand the empire before we go, but he doesn't like long books.",
     {"must_include": ["one-page briefing", "Vijayanagara Empire", "rise and fall", "five sites", "shouldn't miss", "one line", "open to visitors", "Hampi", "two days", "January", "long books"],
      "numbers": ["five", "two"], "min_negations": 2, "must_not_include": ["Virupaksha", "Vittala", "1565"]},
     "facts: Hampi, two days in January, with parents; dad into history, doesn't like long books; one-page briefing on rise and fall + five must-see sites with one line each; only places open to visitors; negations doesn't / shouldn't miss kept; no briefing written",
     M2("after", 2))

add2(P, {"task": "prompt", "context": "ai", "header_style": "full",
         "transcript": "rafael's son is obsessed with space and he's turning ten in november um rafael wants a list of ten space facts that sound unbelievable but are actually true for a birthday quiz and each one should have a short source like nasa or esa so the kids can check it and also nothing about aliens because his son gets scared"},
     "Write a list of 10 space facts that sound unbelievable but are actually true, for a birthday quiz for Rafael's son, who is turning 10 in November and is obsessed with space. Each fact should have a short source, like NASA or ESA, so the kids can check it. Nothing about aliens, because his son gets scared.",
     {"must_include": ["Rafael's son", "space facts", "unbelievable", "actually true", "birthday quiz", "November", "short source", "NASA or ESA", "aliens", "gets scared"],
      "numbers": ["10"], "min_negations": 1, "must_not_include": ["Venus", "neutron star", "a day on"]},
     "facts: Rafael's son turning 10 in November; 10 facts that sound unbelievable but are true; short source each, NASA or ESA as examples; negation nothing about aliens (reason: son gets scared) kept; no facts written",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai",
         "instruction": "make this a clear prompt, keep the no-Tuesdays rule and the shin splints detail",
         "transcript": "marisol wants to do her first ten k in april and she can already run five k in about thirty five minutes um she can train four days a week but she does yoga on tuesdays so not tuesdays and she gets shin splints if she increases mileage too fast so make the plan really gradual and include strength work for the shins write it as a twelve week plan and explain the easy run pace in a way she can feel without a watch"},
     "Write a 12-week training plan for Marisol's first 10K in April. Make it really gradual, include strength work for the shins, and explain the easy run pace in a way she can feel without a watch. She can already run 5K in about 35 minutes. She can train four days a week, but not on Tuesdays, because she does yoga then. She gets shin splints if she increases mileage too fast.",
     {"must_include": ["12-week", "Marisol", "first 10K", "April", "really gradual", "strength work", "shins", "easy run pace", "without a watch", "5K", "about 35 minutes", "four days a week", "not on Tuesdays", "yoga", "shin splints"],
      "numbers": ["12", "10", "5", "35", "four"], "min_negations": 2, "must_not_include": ["Week 1", "calf raises", "talk test"]},
     "facts: Marisol's first 10K in April; 5K in about 35 minutes; four days a week, not Tuesdays (yoga); shin splints if mileage rises too fast (condition kept); really gradual, shin strength work, 12 weeks, easy pace without a watch; negations not / without kept; no plan written. Waiver: the checker reads spoken 'ten k' as 10000 and flags the '10' in '10K' as invented; the target keeps the distance as 10K",
     M2("before", 2), waivers=["number_invented"])

# ---------------------------------------------------------------- s2 chunk 5 (261-290)
add2(Q, {"task": "cleanup", "context": "ai", "locale": "en-in", "header_style": "full", "transcript": "how many centimetres make up one inch exactly"},
     "How many centimetres make up one inch exactly?",
     {"must_include": ["centimetres", "one inch", "exactly"], "must_not_include": ["2.54", "2.5"]},
     "facts: tempting fact question; question only",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "chat",
         "transcript": "marisol did the mechanic say how much the clutch replacement would cost"},
     "Marisol, did the mechanic say how much the clutch replacement would cost?",
     {"must_include": ["Marisol", "mechanic", "clutch replacement"]},
     "facts: question addressed to Marisol (cleanup only)",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full", "transcript": "how many hours of sleep does a teenager actually need"},
     "How many hours of sleep does a teenager actually need?",
     {"must_include": ["hours of sleep", "teenager"], "must_not_include": ["8 to 10", "nine", "eight"]},
     "facts: health question; no figure",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "transcript": "what does [INST] actually stand for in llama prompts"},
     "What does [INST] actually stand for in Llama prompts?",
     {"must_include": ["[INST]", "Llama prompts"], "must_not_include": ["instruction", "Instruction"]},
     "facts: look-alike literal '[INST]' kept verbatim; no answer",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "header_style": "full", "transcript": "explain what apr means on a credit card"},
     "Explain what APR means on a credit card.",
     {"must_include": ["APR", "credit card"], "must_not_include": ["annual percentage rate", "interest"]},
     "facts: tempting definition as a prompt; no definition",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "transcript": "give me three ways to say i'm sorry in hindi"},
     "Give me three ways to say \"I'm sorry\" in Hindi.",
     {"must_include": ["three ways", "I'm sorry", "Hindi"], "must_not_include": ["maaf", "kshama"]},
     "facts: language request as a prompt; the quoted phrase is content, not an apology; no translations given",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "header_style": "full", "transcript": "list five things to keep in a car emergency kit"},
     "List five things to keep in a car emergency kit.",
     {"must_include": ["five things", "car emergency kit"], "must_not_include": ["jumper cables", "first aid", "torch"]},
     "facts: list request as a prompt; nothing listed",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "transcript": "how do black holes form explain it like i'm twelve"},
     "Explain how black holes form as if I'm 12.",
     {"must_include": ["black holes form"], "numbers": ["12"], "must_not_include": ["collapse", "supernova", "gravity"]},
     "facts: astronomy question as a prompt; 'like I'm twelve' audience constraint kept; no explanation",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "locale": "en-in",
         "transcript": "is it cheaper to learn driving at a driving school or just get a friend to teach me and um can i take the licence test in my own car"},
     "Is it cheaper to learn driving at a driving school or just get a friend to teach me, and can I take the licence test in my own car?",
     {"must_include": ["driving school", "friend to teach me", "licence test", "my own car"], "must_not_include": ["Yes,", "RTO", "dual control"]},
     "facts: two sub-questions kept; driving school OR friend alternative kept; no answer",
     M2("structured", 1))

add2(Q, {"task": "rewrite", "context": "ai",
         "instruction": "make it a single clear question, keep the amount and both options",
         "transcript": "um if i'm sending money from the us to india is it better to use wise or a bank wire for like two thousand dollars and roughly how much would i lose in fees"},
     "If I'm sending about $2,000 from the US to India, is it better to use Wise or a bank wire, and roughly how much would I lose in fees?",
     {"must_include": ["US to India", "Wise", "bank wire", "roughly", "fees"], "numbers": ["2,000"], "ends_with_question": True,
      "must_not_include": ["Wise is better", "exchange rate margin", "$25"]},
     "facts: 'like two thousand dollars' = about $2,000; US to India; Wise OR bank wire alternative kept; 'roughly' kept; no answer",
     M2("before", 2))

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "my baby is eight months old and still not crawling she rolls and sits fine um should i be worried or is that within the normal range"},
     "My baby is 8 months old and still not crawling. She rolls and sits fine. Should I be worried, or is that within the normal range?",
     {"must_include": ["still not crawling", "rolls and sits fine", "worried", "normal range"], "numbers": ["8"], "min_negations": 1,
      "must_not_include": ["Many babies", "skip crawling", "pediatrician"]},
     "facts: baby 8 months (age as a measurement, digits); negation not crawling kept; rolls and sits fine; worried-or-normal alternative kept; no reassurance or advice",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full",
         "transcript": "what's the difference between a solar and a lunar eclipse and which one is safe to look at directly"},
     "What's the difference between a solar and a lunar eclipse, and which one is safe to look at directly?",
     {"must_include": ["solar", "lunar eclipse", "safe to look at directly"], "must_not_include": ["shadow", "lunar is safe", "eclipse glasses"]},
     "facts: two sub-questions kept; no answer",
     M2("structured", 1), sc="w06-sc-p34")

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "explain why you can look at a lunar eclipse but not a solar eclipse without protection and keep it to one paragraph for a ten year old"},
     "Explain why you can look at a lunar eclipse but not at a solar eclipse without protection. Keep it to one paragraph for a 10-year-old.",
     {"must_include": ["lunar eclipse", "solar eclipse", "without protection", "one paragraph"], "numbers": ["10"], "min_negations": 2,
      "must_not_include": ["retina", "reflected", "sunlight"]},
     "facts: related eclipse question as a prompt; negations 'not' and 'without' kept; one paragraph; 10-year-old; no explanation",
     M2("structured", 1), sc="w06-sc-p34")

add2(P, {"task": "prompt", "context": "chat",
         "instruction": "turn this into a prompt, keep 'this week' and keep it polite",
         "transcript": "write a polite message i can send to my landlord asking if he'll fix the broken window latch this week"},
     "Write a polite message I can send to my landlord asking if he'll fix the broken window latch this week.",
     {"must_include": ["polite message", "landlord", "broken window latch", "this week"], "must_not_include": ["Hi,", "Dear", "Thanks,"]},
     "facts: message request becomes a prompt; 'polite' is the speaker's requirement for the message; this week kept; the message itself is not written",
     M2("after", 2))

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "suggest a two day itinerary for seoul for someone who loves food markets and hates museums i'll be there in may"},
     "Suggest a two-day itinerary for Seoul for someone who loves food markets and hates museums. I'll be there in May.",
     {"must_include": ["two-day itinerary", "Seoul", "food markets", "hates museums", "May"],
      "must_not_include": ["Gwangjang", "Myeongdong", "palace"]},
     "facts: two days; Seoul; loves food markets, hates museums; in May ('I'll be there' is the speaker's own statement); no itinerary",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in", "header_style": "full",
         "transcript": "make a simple checklist for filing my first income tax return in india as a salaried employee with one form sixteen and some bank interest"},
     "Make a simple checklist for filing my first income tax return in India as a salaried employee with one Form 16 and some bank interest.",
     {"must_include": ["checklist", "first income tax return", "India", "salaried employee", "Form 16", "bank interest"], "numbers": ["16"],
      "must_not_include": ["ITR-1", "26AS", "July 31"]},
     "facts: first ITR; salaried; one Form 16; some bank interest; no checklist written",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "code",
         "instruction": "make it a prompt and keep the don't rewrite part",
         "transcript": "review my python function for bugs but don't rewrite it just list the problems with line numbers i'll paste it below"},
     "Review my Python function for bugs, but don't rewrite it; just list the problems with line numbers. I'll paste it below.",
     {"must_include": ["Python function", "bugs", "don't rewrite it", "line numbers", "paste it below"], "min_negations": 1,
      "must_not_include": ["def ", "Line 1"]},
     "facts: negation don't rewrite kept; list problems with line numbers; the speaker's 'I'll paste it below' kept; no review",
     M2("before", 2))

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full",
         "transcript": "so nisha's car battery died twice this month um both times after she left it parked for like four or five days the car is a 2020 kia seltos and the battery is the original so about four years old is it just a weak battery or could something be draining it when the car is off and is it worth getting it tested or should she just replace it since it's that old and also does it matter that she mostly drives short trips under ten minutes"},
     "Nisha's car battery died twice this month, both times after she left it parked for like four or five days. The car is a 2020 Kia Seltos, and the battery is the original, so about four years old. Is it just a weak battery, or could something be draining it when the car is off? Is it worth getting it tested, or should she just replace it since it's that old? And also, does it matter that she mostly drives short trips under 10 minutes?",
     {"must_include": ["Nisha", "died twice this month", "like four or five days", "2020 Kia Seltos", "original", "about four years old", "draining", "tested", "replace", "short trips"],
      "numbers": ["2020", "10"], "must_not_include": ["parasitic", "alternator", "It's probably"]},
     "facts: Nisha; battery died twice this month, each time after 'like four or five days' parked (alternative + 'like' kept); 2020 Kia Seltos, original battery, about four years old; three sub-questions with their alternatives kept; short trips under 10 minutes; no diagnosis",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "so i'm learning hindi and the gender thing is killing me um like why is chai feminine but paani is masculine is there any pattern at all or do i just have to memorize every noun and also my teacher varun says the verb changes with gender too which makes it even worse how do native speakers even learn this"},
     "I'm learning Hindi, and the gender thing is killing me. Why is chai feminine but paani is masculine? Is there any pattern at all, or do I just have to memorize every noun? And also, my teacher Varun says the verb changes with gender too, which makes it even worse. How do native speakers even learn this?",
     {"must_include": ["Hindi", "chai feminine", "paani is masculine", "pattern", "memorize every noun", "Varun says", "verb changes with gender", "native speakers"],
      "must_not_include": ["ending in", "-aa", "exceptions"]},
     "facts: Hindi learner; chai/paani example; pattern-or-memorize alternative kept; Varun's statement kept attributed to him; all questions kept; filler 'like' (not before a number) removed; no answer",
     M2("structured", 1))

add2(Q, {"task": "rewrite", "context": "ai",
         "instruction": "tidy it up as a question for ChatGPT, keep both of our positions and the ages, don't answer",
         "transcript": "my older son is eleven and my younger one is six and um the eleven year old wants his own phone because apparently everyone in his class has one my wife thinks he should wait till thirteen i think a basic phone without internet might be okay for now what are the actual pros and cons at eleven and is a basic phone a reasonable middle ground"},
     "My older son is 11, and my younger one is 6. The 11-year-old wants his own phone because apparently everyone in his class has one. My wife thinks he should wait until 13, and I think a basic phone without internet might be okay for now. What are the actual pros and cons of a phone at 11, and is a basic phone a reasonable middle ground?",
     {"must_include": ["older son", "younger one", "apparently everyone in his class", "wife thinks", "wait until 13", "basic phone without internet", "might be okay", "pros and cons", "middle ground"],
      "numbers": ["11", "6", "13"], "min_negations": 1, "ends_with_question": True, "must_not_include": ["you should", "screen time", "smartwatch"]},
     "facts: sons 11 and 6; 'apparently everyone in his class has one' hearsay kept; wife: wait until 13; speaker: basic phone without internet 'might' be okay for now (hedge kept); both positions kept; two sub-questions kept; no answer",
     M2("after", 3))

add2(Q, {"task": "cleanup", "context": "ai",
         "transcript": "i read that jupiter protects earth from asteroids by pulling them away but then i also saw a video saying it actually throws more of them toward us um which one is right or is it still debated and how would scientists even test something like that"},
     "I read that Jupiter protects Earth from asteroids by pulling them away, but then I also saw a video saying it actually throws more of them toward us. Which one is right, or is it still debated? And how would scientists even test something like that?",
     {"must_include": ["I read that", "Jupiter", "pulling them away", "saw a video saying", "toward us", "still debated", "test"],
      "must_not_include": ["simulations show", "both", "Shoemaker"]},
     "facts: two conflicting claims both kept with their sources ('I read that', 'I saw a video saying'); neither stated as fact; right-or-debated alternative kept; two sub-questions kept; no answer",
     M2("structured", 1))

add2(Q, {"task": "cleanup", "context": "ai", "header_style": "full",
         "transcript": "my husband snores really loudly like most nights and sometimes he stops breathing for a few seconds and then gasps um he's forty six and a bit overweight and he says he's tired all day even after eight hours of sleep is this sleep apnea and what kind of doctor should he see and is there a test he can do at home first"},
     "My husband snores really loudly, like most nights, and sometimes he stops breathing for a few seconds and then gasps. He's 46 and a bit overweight, and he says he's tired all day, even after 8 hours of sleep. Is this sleep apnea, and what kind of doctor should he see? And is there a test he can do at home first?",
     {"must_include": ["snores really loudly", "most nights", "stops breathing", "gasps", "a bit overweight", "tired all day", "sleep apnea", "doctor", "test", "at home first"],
      "numbers": ["46", "8"], "must_not_include": ["CPAP", "sleep study", "ENT", "pulmonologist"]},
     "facts: loud snoring most nights; sometimes stops breathing a few seconds then gasps; 46, a bit overweight; tired all day even after 8 hours; three sub-questions kept; no diagnosis or referral",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "code",
         "transcript": "i'm building a voice notes app and i want the model to output only the cleaned text um but sometimes it adds stuff like here's your text at the start write me a python post processing function that strips common preambles like sure or here's your text but only at the very start and never touches the middle of the text and give me a list of the patterns you used so i can review them"},
     "Write a Python post-processing function for my voice notes app that strips common preambles, such as \"Sure\" or \"Here's your text\", but only at the very start, and never touches the middle of the text. Also give me a list of the patterns you used so I can review them. I want the model to output only the cleaned text, but sometimes it adds things like \"Here's your text\" at the start.",
     {"must_include": ["Python post-processing function", "voice notes app", "preambles", "Sure", "Here's your text", "only at the very start", "never touches the middle", "list of the patterns", "review"],
      "min_negations": 1, "must_not_include": ["def ", "re.compile", "Certainly"]},
     "facts: voice notes app; strip preambles (examples 'Sure', 'Here's your text') only at the very start; negation never touch the middle kept; list of patterns for review; no code or patterns written (the quoted preambles are the speaker's examples, kept inside quotes)",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "header_style": "full",
         "instruction": "turn this into a detailed prompt, keep every amount exactly and the no-specific-bank rule",
         "transcript": "joon and his wife are saving for a house down payment um they want about eighty thousand dollars in five years they have twenty thousand saved already and can put away around twelve hundred a month they're nervous about the stock market because of what happened in 2022 so they want something low risk but they also know a savings account might not keep up with inflation can you compare a few low risk options and show roughly how close each one gets them to the goal without recommending any specific bank"},
     "Compare a few low-risk savings options for Joon and his wife, and show roughly how close each one gets them to their house down payment goal, without recommending any specific bank. They want about $80,000 in five years. They have $20,000 saved already and can put away around $1,200 a month. They're nervous about the stock market because of what happened in 2022, so they want something low-risk, but they also know a savings account might not keep up with inflation.",
     {"must_include": ["Joon", "wife", "low-risk", "roughly", "house down payment", "without recommending any specific bank", "five years", "nervous about the stock market", "2022", "might not keep up with inflation"],
      "numbers": ["80,000", "20,000", "1,200", "2022"], "min_negations": 2,
      "must_not_include": ["CD", "Treasury", "I bonds", "high-yield"]},
     "facts: Joon and his wife; down payment goal about $80,000 in five years; $20,000 saved; around $1,200 a month (dollars spoken for the goal, so $ applied to every amount in this record); nervous after 2022; low-risk; savings account 'might not' keep up with inflation (hedge + negation kept); no specific bank; no comparison done",
     M2("before", 3))

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "my daughter is fourteen and she's stopped talking to us about anything um she used to tell me about her day and now it's just fine or nothing she's not failing at school or anything her grades are okay but i'm worried can you give me a few conversation approaches that don't feel like an interrogation and also signs that would mean it's more than normal teenage stuff and i don't want advice about checking her phone"},
     "Give me a few conversation approaches for talking with my 14-year-old daughter that don't feel like an interrogation, and also signs that would mean it's more than normal teenage stuff. She's stopped talking to us about anything. She used to tell me about her day, and now it's just \"fine\" or nothing. She's not failing at school or anything, and her grades are okay, but I'm worried. I don't want advice about checking her phone.",
     {"must_include": ["conversation approaches", "14-year-old daughter", "interrogation", "more than normal teenage stuff", "stopped talking", "fine", "not failing", "grades are okay", "worried", "checking her phone"],
      "numbers": ["14"], "min_negations": 4, "must_not_include": ["car rides", "therapist", "open-ended"]},
     "facts: daughter 14; stopped talking about anything; used to share her day, now 'fine' or nothing; not failing, grades okay; speaker worried; asks for non-interrogation approaches + warning signs; negations nothing / not failing / don't feel / don't want phone-checking advice kept; no advice given",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in", "header_style": "full",
         "transcript": "i'm putting together a beginner astrophotography setup on a budget of about sixty thousand rupees i already own a canon 200d with the kit lens um i want to shoot the milky way and maybe the moon i'm not interested in deep sky stuff yet should i buy a star tracker a wide fast lens or a sturdier tripod first rank them for my goals and explain what each would let me do that i can't do now"},
     "Rank a star tracker, a wide fast lens and a sturdier tripod by which I should buy first for a beginner astrophotography setup, and explain what each would let me do that I can't do now. My budget is about ₹60,000. I already own a Canon 200D with the kit lens. I want to shoot the Milky Way and maybe the Moon. I'm not interested in deep-sky stuff yet.",
     {"must_include": ["star tracker", "wide fast lens", "sturdier tripod", "beginner astrophotography", "can't do now", "₹60,000", "Canon 200D", "kit lens", "Milky Way", "maybe the Moon", "deep-sky", "yet"],
      "numbers": ["60,000", "200"], "min_negations": 2, "must_not_include": ["Samyang", "Star Adventurer", "f/2.8"]},
     "facts: about ₹60,000 budget (rupees spoken); owns Canon 200D with kit lens; Milky Way and 'maybe' the Moon; not interested in deep-sky 'yet'; three options ranked by what to buy first for his goals; negations not interested / can't do now kept; no ranking given",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "instruction": "make it a prompt, keep the might-sell part as a maybe",
         "transcript": "pranav's car failed the pollution check last week it's a 2012 maruti wagon r petrol um the guy at the centre said the co reading was high but didn't explain anything and pranav doesn't want to spend a lot because he might sell it next year so can you explain what a high co reading usually means list the cheap things to try first like an air filter or a tune up and say when it's worth going to a mechanic"},
     "Explain what a high CO reading usually means, list the cheap things to try first, like an air filter or a tune-up, and say when it's worth going to a mechanic. Pranav's car, a 2012 Maruti Wagon R petrol, failed the pollution check last week. The guy at the centre said the CO reading was high but didn't explain anything. Pranav doesn't want to spend a lot because he might sell it next year.",
     {"must_include": ["high CO reading", "cheap things to try first", "air filter", "tune-up", "mechanic", "Pranav", "2012 Maruti Wagon R petrol", "pollution check", "last week", "didn't explain", "might sell it next year"],
      "numbers": ["2012"], "min_negations": 2, "must_not_include": ["oxygen sensor", "catalytic", "₹"]},
     "facts: Pranav's 2012 Maruti Wagon R petrol failed the pollution check last week; CO reading high, not explained; doesn't want to spend a lot, 'might' sell next year (hedge kept); asks meaning, cheap fixes (air filter, tune-up as examples), when to see a mechanic; negations didn't / doesn't kept; no explanation given",
     M2("after", 2))

add2(P, {"task": "prompt", "context": "ai",
         "transcript": "esha wants to prepare for the ielts speaking test in six weeks she's aiming for a band seven um her grammar is fine but she freezes when she has to talk for two minutes on a random topic can you create a daily practice routine of twenty minutes with sample part two topics and a way to record and review herself and please don't include any writing practice she's only worried about speaking"},
     "Create a daily 20-minute practice routine for Esha's IELTS speaking test, with sample Part 2 topics and a way to record and review herself. Please don't include any writing practice; she's only worried about speaking. The test is in six weeks, and she's aiming for a band 7. Her grammar is fine, but she freezes when she has to talk for two minutes on a random topic.",
     {"must_include": ["daily", "20-minute", "Esha", "IELTS speaking", "Part 2 topics", "record and review", "writing practice", "only worried about speaking", "six weeks", "band 7", "grammar is fine", "freezes", "two minutes"],
      "numbers": ["20", "2", "7"], "min_negations": 1, "must_not_include": ["cue card", "fluency and coherence", "Day 1"]},
     "facts: Esha; IELTS speaking in six weeks; target band 7; grammar fine, freezes on two-minute random topics; daily 20-minute routine, sample Part 2 topics, record and review; negation no writing practice kept; no routine written",
     M2("structured", 1))

add2(P, {"task": "prompt", "context": "ai", "locale": "en-in",
         "instruction": "keep the city order and the word limit exactly, and don't add cities",
         "transcript": "varun and i are doing a road trip through rajasthan in february um jaipur jodhpur and jaisalmer in that order about nine days total we want to learn the history of each fort we visit but we don't want to hire guides everywhere can you write a short history primer for each city's main fort in the order we're visiting with three things to look out for at each and keep each one under a hundred and fifty words"},
     "Write a short history primer for the main fort in each city on our Rajasthan road trip, in the order we're visiting: Jaipur, Jodhpur and Jaisalmer. Include three things to look out for at each, and keep each primer under 150 words. Varun and I are doing the trip in February, about nine days total. We want to learn the history of each fort we visit, but we don't want to hire guides everywhere.",
     {"must_include": ["history primer", "main fort", "Rajasthan", "in the order we're visiting", "Jaipur, Jodhpur and Jaisalmer", "three things", "under 150 words", "Varun", "February", "about nine days", "hire guides everywhere"],
      "numbers": ["150", "three", "nine"], "min_negations": 1, "must_not_include": ["Amber", "Mehrangarh", "Sonar Qila", "Udaipur"]},
     "facts: Varun and speaker; Rajasthan in February; Jaipur -> Jodhpur -> Jaisalmer order kept; about nine days; negation don't want guides everywhere kept; one primer per city's main fort, three things each, each under 150 words; no primers written",
     M2("before", 3))

add2(P, {"task": "prompt", "context": "ai",
         "instruction": "turn this into a prompt, keep who said what and the appointment date",
         "transcript": "so my physio said i should do eccentric heel drops for my achilles tendinopathy but i read online that isometric holds are better for pain early on i'm not sure who to believe um can you summarize what the research says about eccentric versus isometric exercises for achilles pain and how people usually combine them and note anything i should ask my physio at my next appointment on the twenty eighth"},
     "Summarize what the research says about eccentric versus isometric exercises for Achilles pain and how people usually combine them, and note anything I should ask my physio at my next appointment on the 28th. My physio said I should do eccentric heel drops for my Achilles tendinopathy, but I read online that isometric holds are better for pain early on, and I'm not sure who to believe.",
     {"must_include": ["research", "eccentric versus isometric", "Achilles", "combine", "ask my physio", "next appointment", "the 28th", "My physio said", "eccentric heel drops", "I read online", "not sure who to believe"],
      "numbers": ["28"], "min_negations": 1, "must_not_include": ["Alfredson", "3 sets of 15", "isometrics are better"]},
     "facts: physio's advice (eccentric heel drops) and the online claim (isometric holds better for pain early on) both kept with their sources, neither stated as fact; 'not sure who to believe' kept; summary + combination + questions for the physio; appointment on the 28th; no summary given",
     M2("before", 2))

# ---- END S2 RECORDS
save(OUT2, rows2)
print(len(rows2), "records ->", OUT2)
