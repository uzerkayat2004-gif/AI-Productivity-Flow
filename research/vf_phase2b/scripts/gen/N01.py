"""N01 generator: S1-mini native-cleanup REHEARSAL pool, inputs + independent fact annotations only.

Writes research/vf_phase2b/data/native/native_in.jsonl (480 rows). NO targets: targets come from the real
S1-mini model (scripts/s1_native_generate.py) and are reviewed/corrected afterwards.

Row: {"id": "NR-0001", "native_control": "[Styling: X] [Structure: Y] [Context: Z]", "transcript": ...,
      "assertions": {...}, "note": ..., "scenario_id": "n01-sc-NNNN"}

Control distribution (what the app sends): Styling semi-formal ~65% / formal ~35%; Structure lists only for
rows that dictate 3+ items or list cues (~18%); Context email only for dictated-email rows (~15%).

Item DSL (one per line in DATA):  tags|transcript|numbers|numbers_one_of|must_include|must_not_include|min_neg|note
  tags: e=email context, l=lists structure, n=numbers, g=negation, h=hedge/condition, c=self-correction,
        a=genuine alternative, p=spoken punctuation, i=Indian English, q=question (must stay a question), t=technical
  lists split on ';'. A must_include item containing '/' (not a URL) becomes a must_include_one_of group. numbers_one_of: groups split on ';', alternatives on '~' if present else '/'.
Fully deterministic: re-running reproduces the file byte for byte.
"""
import json
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "data", "native", "native_in.jsonl"))
SEED = 20261012
N_EXPECTED = 480
FORMAL_SHARE = 0.35

CTRL_RE = re.compile(r"^\[Styling: (semi-formal|formal)\] \[Structure: (prose|lists)\] \[Context: (general|email)\]$")


def _split(s):
    return [x.strip() for x in s.split(";") if x.strip()]


def parse(data):
    items = []
    for line in data.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        assert len(parts) == 8, (len(parts), line)
        tags, tr, nums, oneof, inc, exc, neg, note = parts
        groups = []
        for g in _split(oneof):
            alts = [a.strip() for a in (g.split("~") if "~" in g else g.split("/")) if a.strip()]
            groups.append(alts)
        include, include_one_of = [], []
        for x in _split(inc):
            if "/" in x and "://" not in x:
                include_one_of.append([y.strip() for y in x.split("/") if y.strip()])
            else:
                include.append(x)
        items.append(dict(tags=tags.strip(), transcript=tr.strip(), numbers=_split(nums), one_of=groups,
                          include=include, include_one_of=include_one_of, exclude=_split(exc),
                          neg=int(neg or 0), note=note.strip()))
    return items


def length_class(t):
    n = len(t.split())
    return "short" if n < 15 else ("medium" if n <= 50 else "long")


def build():
    items = parse(DATA)
    assert len(items) == N_EXPECTED, len(items)
    rng = random.Random(SEED)
    order = list(range(len(items)))
    rng.shuffle(order)
    n_formal = round(FORMAL_SHARE * len(items))
    formal_idx = set(rng.sample(range(len(items)), n_formal))
    rows = []
    for k, i in enumerate(order, 1):
        it = items[i]
        tags = it["tags"]
        styling = "formal" if i in formal_idx else "semi-formal"
        structure = "lists" if "l" in tags else "prose"
        context = "email" if "e" in tags else "general"
        ctrl = f"[Styling: {styling}] [Structure: {structure}] [Context: {context}]"
        a = {"behavior": "not_answer" if "q" in tags else "transform", "no_markdown": True}
        if it["numbers"]:
            a["numbers"] = it["numbers"]
        if it["one_of"]:
            a["numbers_one_of"] = it["one_of"]
        if it["include"]:
            a["must_include"] = it["include"]
        if it["include_one_of"]:
            a["must_include_one_of"] = it["include_one_of"]
        if it["exclude"]:
            a["must_not_include"] = it["exclude"]
        if it["neg"]:
            a["min_negations"] = it["neg"]
        if "q" in tags and not ("e" in tags or "l" in tags) and length_class(it["transcript"]) != "long":
            a["ends_with_question"] = True
        keep = (it["include"] + ["/".join(g) for g in it["include_one_of"]] + it["numbers"]
                + ["/".join(g) for g in it["one_of"]])
        note = "facts: " + "; ".join(keep)
        if it["note"]:
            note = it["note"] + " | " + note
        if it["neg"]:
            note += f" | negations kept (>= {it['neg']})"
        rows.append({"id": f"NR-{k:04d}", "native_control": ctrl, "transcript": it["transcript"],
                     "assertions": a, "note": note, "scenario_id": f"n01-sc-{i + 1:04d}",
                     "_features": sorted(set(tags)), "_length": length_class(it["transcript"])})
    for r in rows:
        assert CTRL_RE.match(r["native_control"]), r
    assert len({r["id"] for r in rows}) == len(rows)
    assert len({r["transcript"] for r in rows}) == len(rows)
    return rows


def main():
    rows = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({k: v for k, v in r.items() if not k.startswith("_")}, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows -> {OUT}")
    stats(rows)


def stats(rows):
    from collections import Counter
    n = len(rows)
    for name, key in (("styling", lambda r: r["native_control"].split("]")[0][10:]),
                      ("structure", lambda r: r["native_control"].split("[Structure: ")[1].split("]")[0]),
                      ("context", lambda r: r["native_control"].split("[Context: ")[1].split("]")[0]),
                      ("length", lambda r: r["_length"])):
        c = Counter(key(r) for r in rows)
        print(name, {k: f"{v} ({100 * v / n:.0f}%)" for k, v in sorted(c.items())})
    names = dict(n="numbers", g="negation", h="hedge/condition", c="self-correction", a="alternative",
                 p="spoken punct", i="Indian English", q="question", t="technical", e="email", l="lists")
    c = Counter(f for r in rows for f in r["_features"])
    print("features", {names[k]: f"{v} ({100 * v / n:.0f}%)" for k, v in sorted(c.items())})
    det = dict(
        negation=lambda r: bool(r["assertions"].get("min_negations")),
        self_correction=lambda r: bool(re.search(r"\b(no wait|sorry|i mean|scratch|actually|or rather|correction|wait no|oh wait|"
                                                 r"hold on|hang on|make it|make that|hmm no|no no)\b", r["transcript"])),
        hedge_condition=lambda r: bool(re.search(r"\b(might|maybe|probably|i think|if|unless|perhaps|possibly|likely|guess|"
                                                 r"reckon|suppose|apparently|seems|hopefully|assuming|roughly|i'd say)\b",
                                                 r["transcript"])),
        spoken_punct=lambda r: bool(re.search(r"\b(comma|full stop|question mark|new line|exclamation mark|new paragraph|"
                                              r"colon)\b", r["transcript"])),
        indian_english=lambda r: bool(re.search(r"\b(yaar|prepone|preponed|kindly|do the needful|revert|itself|lakh|crore|"
                                                r"haan|accha|arre|bhai|aunty|nani|mama|masi|mummy|papa|dhaba|out of station|"
                                                r"cousin brother|pg|puja|diwali|navratri|tiffin|dhobi|watchman|society|na)\b",
                                                r["transcript"])),
        question=lambda r: r["assertions"]["behavior"] == "not_answer",
        alternative=lambda r: "a" in r["_features"],
        technical=lambda r: "t" in r["_features"],
    )
    print("detected (content-based)", {k: f"{sum(map(f, rows))} ({100 * sum(map(f, rows)) / n:.0f}%)"
                                       for k, f in det.items()})
    nn = sum(1 for r in rows if r["assertions"].get("numbers") or r["assertions"].get("numbers_one_of"))
    print(f"rows with number assertions: {nn} ({100 * nn / n:.0f}%)")


DATA = r'''
# ---- SHORT rows (<15 words) ----
in|um the bike servicing is booked for saturday ten thirty, i'll drop it at the showroom only|10:30||bike servicing;Saturday;showroom;only||0|
g|we we don't need the extra chairs anymore|||extra chairs||1|
q|is the projector in room six still broken question mark||6/six|projector|question mark|0|question stays a question
in|basically yaar the rent goes up by eighteen hundred from next month itself|1,800/1800||rent;yaar;next month itself||0|
c|call omar no wait call zoya about the keys|||Zoya;keys|Omar|0|correction applied: Zoya, not Omar
g|um i haven't uh haven't heard back from the landlord|||landlord||1|
h|the paint might be dry by tonight i think|||paint;might;tonight||0|hedge 'might' kept
in|my flight lands at six forty five in the morning so kindly send the driver by six thirty|6:45;6:30||flight;morning;kindly;driver||0|
i|yaar the meeting got preponed to eleven|11|preponed/prepone|yaar;meeting||0|Indian English kept; moved earlier to 11
q|uh did anyone did anyone feed the cat this morning|||cat;this morning||0|question stays a question
g|please don't park in the visitor spots|||visitor spots||1|
c|the call is at two sorry three p m|3||call|2|0|correction: 3 p.m., not 2
t|the build fails on node eighteen but passes on twenty|18;20||build;Node||0|both versions kept
p|thanks for the flowers exclamation mark they look amazing|||flowers;amazing|exclamation mark|0|
i|kindly revert by tomorrow evening on the quote|||revert;quote;tomorrow evening||0|Indian English 'revert' kept
n|um the gym is closed from the fifth to the ninth||5th/fifth;9th/ninth|gym;closed||0|
g|nobody signed up for the sunday shift yet|||Sunday shift;yet||1|
q|can we move standup to nine fifteen tomorrow|9:15||standup;tomorrow||0|question stays a question
h|uh maybe we should probably wait for the final numbers|||wait;final numbers;probably||0|hedges 'maybe'/'probably'
n|the hike is about twelve kilometres one way|12||hike;one way;about||0|
a|we need either fifteen or fifty litres of paint|15;50||litres;paint||0|alternative: both 15 and 50 kept
g|i'm not i'm not coming to the potluck sorry|||potluck||1|
c|meet at gate four actually gate seven||7/seven|gate|4;four|0|correction: gate 7, not 4
nh|so the battery lasts roughly nine hours||9/nine|battery;roughly;hours||0|hedge 'roughly' kept
ic|the carpenter no the electrician is coming at four only|4||electrician;only|carpenter|0|correction: electrician, not carpenter; 'only' kept
t|the endpoint is slash api slash v2 slash orders||/api/v2/orders~api slash v2|orders||0|path dictated in words
n|the train leaves platform three at five fifty two|5:52|3/three|train;platform||0|
g|the printer isn't printing double sided again|||printer;double;again||1|
q|who's bringing the speaker for friday|||speaker;Friday||0|question stays a question
in|uh my cousin sister turns twenty one on the twelfth, we're planning a surprise at her PG||12th/twelfth|cousin sister;surprise;PG||0|21 kept
c|the code is four nine one two no sorry four nine two one||4921/4,921|code|4912|0|correction: 4921 only
i|haan i'll send the photos by evening yaar|||photos;yaar;evening||0|
p|first line done new line second line pending|||first line;second line;pending|new line|0|spoken new line converted
g|we can't take the dog on the ferry|||dog;ferry||1|
n|the course costs one hundred forty nine euros|149||course||0|
h|the bus should be here in five minutes or so||5/five|bus;or so;should||0|hedge 'or so' kept
g|uh there's no milk left in the office fridge|||milk;office fridge||1|
c|book it for tuesday scratch that wednesday|||Wednesday|Tuesday|0|correction: Wednesday, not Tuesday
in|we raised twenty three thousand rupees for the flood relief, thank you all so much ji|23,000/23000||flood relief;thank you;ji||0|
t|the token expires after thirty six hundred seconds|3,600/3600||token;seconds||0|
i|my cousin brother is out of station till monday|||cousin brother;out of station;Monday||0|
g|i never got the confirmation email|||confirmation email||1|
n|the movie starts at eight ten so leave by seven thirty|8:10;7:30||movie;leave||0|
h|i guess the trial could run another week|||trial;could;another week||0|hedge kept
q|should i bring my own helmet|||helmet||0|question stays a question
g|don't forget the charger it's not in the bag|||charger;bag||2|
a|the meetup is on the third or the fourth i forget||3rd/third;4th/fourth|meetup;forget||0|alternative: both dates kept
c|order the blue one i mean the green one|||green|blue|0|correction: green only
in|so my CGPA went from six point two to eight point one this sem, mummy is very happy|6.2;8.1||CGPA;this sem;mummy;happy||0|
i|we will do the needful and update the sheet|||do the needful;sheet||0|
t|run npm install then npm run dev|||npm install;npm run dev||0|
g|the store doesn't open until noon on holidays|||store;noon;holidays||1|
q|um is the deadline still the end of the month|||deadline;end of the month||0|question stays a question
in|arre the water bill was nine hundred forty rupees this month, last month it was half only|940||water bill;this month;last month;half only||0|
p|bring snacks comma water comma and sunscreen|||snacks;water;sunscreen|comma|0|spoken commas converted
h|we'll likely finish the draft by thursday|||draft;likely;Thursday||0|hedge 'likely'
g|my phone won't charge past eighty percent|80||phone;charge||1|
c|the venue holds two hundred no three hundred people|300||venue|200|0|correction: 300, not 200
n|the kids' swim class is at quarter past four||4:15/quarter past four|swim class||0|
i|accha so tell him to come by three only|3||only||0|
q|did you renew the car insurance|||car insurance||0|question stays a question
t|ssh into the box at ten dot zero dot zero dot five|10.0.0.5||ssh||0|
pn|we've got seventeen days until the move exclamation mark start packing the books new line and label every box|17||move;packing;books;label every box|exclamation mark;new line|0|
g|the medicine shouldn't be taken on an empty stomach|||medicine;empty stomach||1|
a|pick up six or eight bags of soil||6/six;8/eight|bags of soil||0|alternative: 6 or 8 both kept
h|the shop around the corner might have batteries|||shop;might;batteries||0|
in|uh fifty two percent said yes in the society poll for the new gate timings|52||society poll;new gate timings||0|
c|her number ends in three four oh actually three four eight|348||number|340|0|correction: ends in 348
q|are we still on for lunch on thursday|||lunch;Thursday;still||0|question stays a question
i|my PG owner wants the rent by the fifth||5th/fifth|PG owner;rent||0|
t|the config lives in dot env dot local||.env.local/dot env dot local|config||0|
p|great work today full stop see you tomorrow|||great work;see you tomorrow|full stop|0|
g|i'm not sure the tickets are refundable|||tickets;refundable;not sure||1|
h|apparently the road might be closed tomorrow|||road;might;closed;apparently||0|
q|how many people are coming to the barbecue|||barbecue||0|question stays a question
c|the password reset link goes to kiran sorry to sameer|||Sameer;password reset|Kiran|0|correction: Sameer, not Kiran
n|my resting heart rate is around fifty eight|58||heart rate;around||0|
i|no tension yaar the auto is already booked|||tension;yaar;auto;already||1|
g|we shouldn't reply until legal checks it|||legal;until||1|
q|uh which charger works with the new laptop|||charger;new laptop||0|question stays a question
t|the cron runs every fifteen minutes|15||cron;minutes||0|
a|the dinner is at seven or seven thirty|7:30||dinner||0|alternative: 7 and 7:30 both kept
p|can you call me back question mark it's urgent|||call me back;urgent|question mark|0|
g|the parking lot has no lights at night|||parking lot;lights;at night||1|
n|the package arrives between two and four||2/two;4/four|package;between||0|range 2 to 4 kept
h|i think the meeting room is booked|||I think;meeting room;booked||0|
c|leave at five no wait five thirty|5:30||leave||0|correction: 5:30
q|did the roofer's invoice ever come through|||roofer;invoice||0|question stays a question
i|we'll prepone the review to tuesday|||prepone;review;Tuesday||0|
g|i won't be online after nine tonight|9||online;tonight||1|

# ---- SHORT rows part 2 (email + lists + misc) ----
e|hi joel the slides are uploaded thanks ruth|||Joel;slides;uploaded;Ruth||0|
e|hey marco um the keys are with security cheers lena|||Marco;keys;security;Lena||0|
eg|hi team the gym is not open tomorrow thanks owen|||team;gym;tomorrow;Owen||1|
en|hi clara the refund of forty dollars went through thanks felix|40||Clara;refund;Felix||0|
e|hello mr shah the signed form is attached regards neha|||Shah;signed form;attached;Neha||0|
eq|hi bilal can you share the minutes thanks sana|||Bilal;minutes;Sana||0|request stays a question
ec|hi theo the call is monday no tuesday thanks ivy|||Theo;Tuesday;Ivy|Monday|0|correction: Tuesday, not Monday
en|hi uma your order ships on the ninth thanks oscar||9th/ninth|Uma;order;Oscar||0|
ei|hi vikram sir kindly share the bank details thanks pooja|||Vikram;bank details;Pooja||0|
eh|hi freya i might be a bit late today thanks jonas|||Freya;might;late;Jonas||0|
l|um for the trip we need tents torches and a first aid kit|||tents;torches;first aid kit||0|three items kept
l|the list is apples oranges bananas and grapes|||apples;oranges;bananas;grapes||0|
ln|items for the stall twenty cups ten plates and five jugs|20|10/ten;5/five|cups;plates;jugs||0|
l|to do call the bank pay the electricity bill and book the cab|||bank;electricity bill;cab||0|
l|so pack chargers passports and the travel adapter|||chargers;passports;travel adapter||0|
lg|buy rice lentils and oil but not the big sacks|||rice;lentils;oil;big sacks||1|
l|my top three picks are the red jacket the boots and the scarf|||red jacket;boots;scarf||0|
li|grocery list atta dal paneer and dhaniya|||atta;dal;paneer;dhaniya||0|
l|bullet one fix the login bullet two update docs bullet three deploy|||login;docs;deploy|bullet|0|spoken bullet cues
l|we need volunteers for setup registration and cleanup|||setup;registration;cleanup||0|
n|uh the meeting ran for ninety minutes again|90||meeting;again||0|
g|the lift is not working on floor nine|9|9/nine|lift;floor||1|
q|so is the parking free after six||6/six|parking;free||0|question stays a question
i|bro the match is postponed till next sunday only|||postponed;next Sunday;only||0|
c|text dev no wait text farhan the address|||Farhan;address|Dev|0|correction: Farhan, not Dev
n|we paid eight hundred fifty for the repairs|850||repairs||0|
t|the api key goes in the authorization header|||API key;authorization header||0|
h|the flight could be delayed by an hour|||flight;could;delayed;an hour||0|
p|ok cool exclamation mark see you there|||see you there|exclamation mark|0|
g|she doesn't eat eggs or fish|||eggs;fish||1|
n|the baby was born at three twenty two am|3:22||baby;born||0|
a|we can meet tuesday or wednesday whichever works|||Tuesday;Wednesday;whichever||0|alternative: both days kept
c|it's apartment twelve b sorry twelve d||12D/12 D/12-D|apartment|12B;12 B;12-B|0|correction: 12D, not 12B
i|we are planning one trip to goa in december|||trip;Goa;December||0|Indian English 'one trip' kept as spoken
n|the scooter does forty five kilometres to a litre|45||scooter;litre||0|
g|you don't have to bring anything|||bring anything||1|
h|uh the results should be out sometime next week|||results;should;next week||0|
n|i owe tanvi six hundred rupees for the concert|600||Tanvi;concert||0|
t|merge the branch feature slash dark mode into main|||dark;main;branch||0|
q|whose turn is it to take out the bins|||turn;bins||0|question stays a question
g|i can't find the spare key anywhere|||spare key;anywhere||1|
n|the rice needs eighteen minutes on low heat|18||rice;low heat||0|
p|dear diary new line today was long|||today was long|new line|0|
c|it costs nine ninety nine actually ten ninety nine|10.99||costs|9.99|0|correction: 10.99, not 9.99
i|can you please adjust the timing, i'm getting late yaar|||timing;getting late;yaar||0|
pn|the marathon is on october twenty sixth comma the bib pickup is the day before full stop|26||marathon;October;bib pickup;day before|comma;full stop|0|
h|i suppose we could split the cost|||suppose;could;split the cost||0|
g|there's no rush on the report|||no rush;report||1|
q|how far is the station from the hotel|||station;hotel||0|question stays a question
n|uh the plant needs water every three days||3/three|plant;water;every||0|
a|the fee is either two fifty or three hundred|250;300||fee||0|alternative: 250 or 300 both kept
t|the error code is e five zero three||E503/E 503/503|error code||0|
c|the parcel goes to flat eight um no flat nine||9/nine|parcel|flat 8;flat eight|0|correction: flat 9 only
i|my mama is coming for the weekend|||mama;weekend||0|
g|i haven't paid the credit card bill yet|||credit card bill;yet||1|
n|so the recipe calls for three hundred grams of flour|300||recipe;grams;flour||0|
q|did the electrician leave an invoice|||electrician;invoice||0|question stays a question
h|i'd say we're about eighty percent done|80||about;done||0|hedge 'about'
p|remind me tomorrow comma call the vet|||remind me tomorrow;call the vet|comma|0|
g|the dog hasn't eaten since morning|||dog;since morning||1|
n|my new number is in the group, the old one stops on the thirtieth||30th/thirtieth|new number;old one||0|
c|we leave on the twentieth no the twenty first|21||leave|20|0|correction: 21st, not 20th
t|bump the version to two point three point one|2.3.1||version||0|
i|so i'll come to your place by four thirty itself|4:30||your place;itself||0|
q|um where did you park the car|||park;car||0|question stays a question
g|the oven timer doesn't beep anymore|||oven timer;beep;anymore||1|
h|probably best to leave early on friday|||probably;leave early;Friday||0|
a|we could repaint it grey or white|||grey;white;repaint||0|alternative: both colours kept
pn|the toll was a hundred and fifteen rupees full stop keep the receipt for the claim full stop|115||toll;receipt;claim|full stop|0|
c|ask for the window seat or rather the aisle seat|||aisle seat|window seat|0|correction: aisle seat
q|did you remember to water the tomatoes|||water;tomatoes||0|question stays a question
g|not today, maybe next weekend|||today;maybe;next weekend||1|hedge 'maybe' + negation
t|log in at admin dot example dot com slash login|||example||0|
i|we went for a long drive and had chai at the dhaba|||long drive;chai;dhaba||0|
pn|the hall is booked from nine to one comma and the projector comes at eight thirty full stop|8:30|9/nine;1/one|hall;booked;projector|comma;full stop|0|
p|hey question mark are you up|||are you up|question mark|0|

# ---- MEDIUM rows part A (15-50 words) ----
n|so um i booked the badminton court for thursday from seven to eight and it's uh two hundred forty rupees for the hour which we can split four ways|240||badminton court;Thursday;split||0|7 to 8 kept; 240 split four ways
g|i talked to the landlord and he said he's not going to fix the heater until next month so like we we might need a space heater for now|||landlord;heater;next month;might;space heater||1|negation + hedge 'might' kept
c|the team dinner is on friday at the italian place on fifth street no wait it's the thai place on fifth street sorry|||Friday;Thai place;Fifth Street|Italian|0|correction: Thai place, not Italian
q|um quick question for the group do we need to bring our own rackets on saturday or will the club have some spare ones|||rackets;Saturday;club;spare||0|question stays a question; both options in question kept
n|so the quarterly numbers came in revenue is up eleven percent and churn dropped to like three point two percent which is the lowest it's been all year|11;3.2||revenue;churn;lowest||0|
h|i'm thinking we could maybe push the launch by a week if the testing isn't done but uh let's see what the qa folks say on monday|||push the launch;a week;if;testing;QA;Monday||1|condition 'if the testing isn't done' + hedge kept
i|yaar the society meeting is on sunday at eleven and they want everybody to pay the maintenance of two thousand five hundred before that only|11|2,500/2500|society meeting;Sunday;maintenance;yaar;only||0|
t|so the staging server is at https://staging.example.com and the health check is at slash healthz it should return a two hundred within like five hundred milliseconds|200;500||https://staging.example.com;health check||0|
p|hi everyone comma just a reminder that the potluck is this saturday full stop please bring a dish that serves at least six people full stop||6/six|potluck;Saturday;at least|full stop|0|spoken punctuation converted
n|my mom's medicine is two tablets in the morning and one at night and the refill is due on the twenty third of this month||2/two;1/one/one at night;23rd/23|medicine;morning;night;refill||0|
g|um the vendor said they don't deliver on weekends and they won't accept cash so we'll need to pay by card before thursday|||vendor;weekends;cash;card;Thursday||2|
c|can you put the meeting at three thirty on wednesday uh actually make it four thirty because i have a physio sorry a doctor appointment before|4:30||meeting;Wednesday;doctor appointment|3:30;physio|0|corrections: 4:30 not 3:30; doctor not physio
a|we could either drive down on friday night or take the early train on saturday morning, both work for me honestly|||drive;Friday night;early train;Saturday morning;both||0|alternative: both travel options kept
q|so i wanted to ask has anyone figured out how we're splitting the electricity bill now that sam moved out|||electricity bill;Sam;moved out||0|question stays a question
e|hi peter just wanted to let you know the samples arrived this morning and they look great we'll send feedback by tomorrow thanks maya|||Peter;samples;this morning;feedback;tomorrow;Maya||0|
e|hi anita um the workshop on the fourteenth is confirmed for thirty people and lunch is included thanks rohan|30|14th/fourteenth|Anita;workshop;lunch;Rohan||0|
eg|hello ms kapoor i'm writing to say that i won't be able to attend the review on monday as i'm travelling regards vikram|||Kapoor;review;Monday;travelling;Vikram||1|
ec|hi jasper the budget for the event is twelve thousand no sorry fifteen thousand dollars so plan around that thanks keira|15,000/15000||Jasper;budget;event;Keira|12,000;12000|0|correction: 15,000 not 12,000
eq|hi noah could you check whether the conference room on the third floor is free on thursday afternoon thanks zoe||3rd/third|Noah;conference room;Thursday afternoon;Zoe||0|request stays a question
ei|dear sir as discussed kindly do the needful and share the revised quotation by end of day thanks and regards sneha|||sir;do the needful;revised quotation;end of day;Sneha||0|
en|hi ishaan the cab is booked for five fifteen am and the driver's number is nine eight two zero one four five six seven three thanks devika|5:15|9820145673/98201 45673|Ishaan;cab;driver;Devika||0|
eh|hi amara i think the contract should be ready by wednesday but legal might need an extra day thanks kwame|||Amara;contract;I think;Wednesday;legal;might;extra day;Kwame||0|
l|okay so for the presentation we need to cover the user research the pricing model the competitor analysis and the launch timeline|||user research;pricing model;competitor analysis;launch timeline||0|four items kept
l|things to fix in the apartment the leaking tap in the kitchen the broken blind in the bedroom and the loose handle on the front door|||leaking tap;broken blind;loose handle;front door||0|
ln|for the camping trip list two tents four sleeping bags a gas stove and um about twenty litres of water|20|2/two;4/four|tents;sleeping bags;gas stove;water;about||0|
lg|the action items are update the pricing page email the beta users and don't touch the billing code until finance signs off|||pricing page;beta users;billing code;finance||1|
li|items for diwali shopping diyas rangoli colours sweets from the usual shop and new curtains for the hall|||Diwali;diyas;rangoli;sweets;curtains||0|
l|new line agenda new line one budget review new line two hiring update new line three office move|||agenda;budget review;hiring update;office move|new line|0|spoken new lines
lc|we need three things milk bread and eggs no wait not eggs we have eggs, butter instead|||milk;bread;butter||0|correction: butter replaces eggs; eggs must not be on the list
g|i don't think we should sign the lease without seeing the place in person, nobody's actually been inside it yet|||lease;in person;inside;yet||2|
h|if it rains on sunday we'll probably move the picnic indoors to the community hall otherwise we'll stick with the park|||if it rains;Sunday;probably;community hall;park||0|condition + hedge kept
i|bhai i reached the station but the train is running two hours late so i'll reach by night only don't wait for dinner||2/two|station;train;late;night;only;dinner||1|
t|the bug is in utils slash date dot ts line forty two where we parse the timestamp without the timezone offset|42||timestamp;timezone offset;date||1|
q|hey um does anyone know if the post office near the market is open on saturdays and what time it closes|||post office;market;Saturdays;closes||0|question stays a question
p|so the plan is comma we meet at the main gate at nine comma walk to the lake comma and have lunch there full stop|9||main gate;lake;lunch||0|spoken punctuation converted
c|my appointment is at the clinic on park road on the ninth uh no it's the tenth at ten am|10||appointment;clinic;Park Road|9th;ninth|0|correction: 10th, not 9th
a|the quote came in at either eighteen thousand for the basic plan or twenty four thousand with installation so we need to pick one|18,000/18000;24,000/24000||quote;basic plan;installation||0|alternative: both prices kept
g|um so i i tried resetting the router twice and it still doesn't connect, the lights aren't even blinking|||router;twice;still;lights;blinking||2|
h|the doctor said it's probably just a sprain but if the swelling doesn't go down in three days i should get an x ray||3/three;x-ray/x ray|doctor;probably;sprain;if;swelling||1|condition kept
q|i was wondering if we should invite the neighbours to the housewarming or keep it small this time|||neighbours;housewarming;small||0|question stays a question
i|my nani is coming from lucknow on the fifteenth so can we prepone the movie plan to the thirteenth||15th/fifteenth;13th/thirteenth|nani;Lucknow;prepone;movie plan||0|
t|set the env variable max retries to five and the timeout to thirty seconds then restart the worker|30|5/five|env;retries;timeout;restart the worker||0|
g|honestly i didn't enjoy the book club pick this month, it wasn't bad but it just never grabbed me|||book club;this month;grabbed me||3|
c|tell the group the hike starts at seven sorry six thirty at the north trailhead and bring water|6:30||hike;north trailhead;water|7|0|correction: 6:30, not 7
n|i need to transfer twelve thousand five hundred to the landlord and three thousand to the maid by the first|12,500/12500;3,000/3000|1st/first|landlord;maid||0|
e|hi tom um just a heads up the deploy is moving to thursday night because of the holiday thanks olivia|||Tom;deploy;Thursday night;holiday;Olivia||0|
eg|hi farhan i checked and we haven't received your payment for september yet could you look into it thanks yusuf|||Farhan;payment;September;yet;Yusuf||1|
en|hi chloe the room rate is one hundred thirty nine a night and breakfast costs fifteen extra thanks ethan|139;15||Chloe;room rate;breakfast;Ethan||0|
ep|hi swati comma the files are in the shared drive full stop let me know if anything is missing full stop thanks leo|||Swati;shared drive;missing;Leo|full stop|0|
e|dear dr menon please find attached the reports from last week's tests i'd appreciate your opinion regards alok|||Menon;reports;last week;tests;Alok||0|
eh|hi mateo i might need to reschedule our call to later in the week if the client meeting runs long thanks isla|||Mateo;might;reschedule;if;client meeting;Isla||0|condition kept
l|so the steps are back up the database run the migration check the logs and then flip the feature flag|||back up;migration;logs;feature flag||0|
ln|for the party we need three pizzas two large bottles of soda a cake and like fifty paper cups|50|3/three;2/two|pizzas;soda;cake;paper cups||0|
l|reading list for the holidays a biography of tesla a sci fi novel and that new cookbook everyone talks about|||biography;Tesla;novel;cookbook||0|
lh|packing list maybe a raincoat definitely sunscreen hats and probably a power bank|||raincoat;sunscreen;hats;power bank;maybe;probably||0|hedges per item kept
g|so the delivery guy came but the parcel wasn't there and the tracking still shows out for delivery which makes no sense|||delivery;parcel;tracking;still;no sense||2|
q|can someone explain why the dashboard shows two different totals for the same week||2/two|dashboard;totals;same week||0|question stays a question
i|aunty said the function is at seven pm sharp and we have to wear traditional, she won't adjust the timing this time|7||aunty;function;sharp;traditional;timing||1|
h|it looks like the sale ends tonight, though i'm not totally sure, so we should order soon if we want the discount|||sale;tonight;not totally sure;order soon;if;discount||1|
t|the webhook posts to https://hooks.example.com/payments and retries three times with exponential backoff||3/three|https://hooks.example.com/payments;webhook;exponential backoff||0|
c|the lamp i ordered is seventy centimetres tall i mean seventy inches no wait centimetres sorry centimetres is right|70||lamp;centimetres/centimeters|inches|0|correction resolves to 70 centimetres
a|the flat is either on the fourth floor or the sixth i honestly don't remember which||4th/fourth;6th/sixth|flat;floor;don't remember||1|alternative: 4th and 6th both kept
g|i told the kids no screens before homework and no sweets after eight|8||screens;homework;sweets||2|
e|hi zara the furniture should arrive between ten and two on saturday so someone needs to be home thanks bilal||10/ten;2/two|Zara;furniture;Saturday;home;Bilal||0|delivery window 10 to 2 kept
q|um has the landlord replied about the deposit or should i follow up again|||landlord;deposit;follow up;again||0|question stays a question
n|the conference has twelve hundred attendees and forty two speakers over three days|1,200/1200;42|3/three|conference;attendees;speakers||0|
i|we went to the mall but the parking was full so we came back without shopping only|||mall;parking;full;without;only||1|
p|reminder colon pick up the dry cleaning before six full stop||6/six|reminder;dry cleaning|colon;full stop|0|

# ---- MEDIUM rows part B ----
e|hi kabir um thanks for covering my shift on sunday i owe you one and i'll take your saturday next month cheers tanvi|||Kabir;covering;Sunday;Saturday;next month;Tanvi||0|
en|hi hugo the venue deposit of two thousand dollars is due by the twenty eighth please confirm once it's paid thanks nora|2,000/2000|28th/twenty-eighth|Hugo;venue deposit;Nora||0|
eg|hi team just a reminder that we don't have standup tomorrow because of the offsite and there's no sprint review either thanks paige|||team;standup;tomorrow;offsite;sprint review;Paige||2|
ec|hi silas the interview is at two pm in room b uh correction room c on the second floor thanks quinn|2||Silas;interview;room C;Quinn|room B|0|correction: room C, not B
ei|hi sameer bhai please send the photos from the sangeet ceremony when you get time, everyone is asking for them thanks kiran|||Sameer;photos;sangeet;Kiran||0|
eq|hello mr fernandes could you please let us know whether the invoice can be paid in two instalments regards ritu||2/two|Fernandes;invoice;instalments;Ritu||0|request stays a question
eh|hi elif i'm not a hundred percent sure but i think the shipment left the warehouse yesterday thanks hiro|100||Elif;not a hundred percent sure;I think;shipment;warehouse;yesterday;Hiro||1|hedge kept
en|hi yuki the gym membership renews on the first and it's forty nine ninety nine a month unless you cancel before thanks jonas|49.99|1st/first|Yuki;gym membership;unless;cancel;Jonas||0|condition kept
e|dear professor white thank you for the feedback on my thesis draft i'll send the revised chapter by friday regards simran|||White;feedback;thesis draft;revised chapter;Friday;Simran||0|
ep|hi gabe comma just checking in question mark did the contractor finish the deck question mark thanks bea|||Gabe;checking in;contractor;deck;Bea|question mark|0|
l|for the onboarding doc we should include the wifi details the slack channels the payroll contacts and the parking rules|||wifi;Slack channels;payroll contacts;parking rules||0|
l|um so on monday i have the optician no the eye doctor then the bank then picking up the kids|||Monday;eye doctor;bank;picking up the kids|optician|0|correction: eye doctor; three errands kept
ln|so the budget breakdown is venue forty thousand food twenty five thousand decor ten thousand and miscellaneous five thousand|40,000/40000;25,000/25000;10,000/10000;5,000/5000||venue;food;decor;miscellaneous||0|
l|garden chores this weekend mow the lawn trim the hedges plant the tulip bulbs and clean the bird bath|||mow the lawn;hedges;tulip bulbs;bird bath||0|
li|for the puja we need flowers coconut agarbatti and prasad from the sweet shop near the temple|||puja;flowers;coconut;agarbatti;prasad||0|
lg|my rules for the trip no work emails no late nights and no fast food|||work emails;late nights;fast food||3|
lp|items colon passport comma visa copy comma hotel booking comma and travel insurance|||passport;visa copy;hotel booking;travel insurance|comma;colon|0|
lh|options for the anniversary maybe a weekend in the hills a nice dinner or possibly a pottery class together|||anniversary;hills;dinner;pottery class;maybe;possibly||0|
lt|todo for the release bump the version update the changelog tag v four point one and publish to npm||v4.1/4.1|changelog;npm;release||0|
lc|send the invite to joel tara and ben actually not ben he's away, send it to max instead|||Joel;Tara;Max||0|correction: Max replaces Ben
g|we can't renew the passport online because the old one is damaged so i'll have to go to the office in person, there's no other way|||passport;online;damaged;in person;no other way||2|
h|i reckon the repair will cost somewhere around six or seven thousand but they said they'll confirm after opening it up|||reckon;repair;around;confirm||0|range 6 or 7 thousand kept as estimate
q|uh so before we book anything should we check if the hotel allows pets because we're taking bruno with us|||hotel;pets;Bruno||0|question stays a question
c|the score was three one to us no wait three two, they scored again in the last minute||3-2/3–2/3 to 2|scored again;last minute|3-1;3–1|0|correction: 3-2 final score
i|my boss told me to stay back today to finish the report so i'll be late, please manage dinner yourself na|||boss;stay back;report;late;dinner||0|
t|the regex should match anything like order dash followed by six digits so caret order dash backslash d curly six close curly dollar|||regex;order;six digits||0|
p|dear all comma the office will remain closed on thursday for the festival full stop work from home if needed full stop|||office;closed;Thursday;festival;work from home|comma|0|
n|we sold two hundred thirteen tickets online and another fifty seven at the door so two seventy total|213;57;270||tickets;online;door;total||0|
a|the train is at nine fifteen or nine fifty i keep mixing them up, check before you leave|9:15;9:50||train;check||0|alternative: both times kept
g|i'm not paying for another month of that streaming app we never even watch it|||streaming app;never||2|
h|if the weather holds we might try the longer trail but i doubt we'll have time|||weather;might;longer trail;doubt||0|condition + hedge kept
q|hey do you know if the visa appointment can be rescheduled online or do we have to call them|||visa appointment;rescheduled;online;call||0|question stays a question
c|the meeting with the investors is on the eleventh at the downtown office, wait no the uptown office||11th/eleventh|investors;uptown office|downtown|0|correction: uptown, not downtown
i|we are three people only, so one big auto will do, no need for two cabs|||three people;auto;cabs||1|
t|the database password is stored in vault at secret slash prod slash db and rotates every ninety days|90||vault;database password;rotates||0|
n|the pressure cooker needs three whistles for the chana and two for the rice||3/three;2/two|pressure cooker;whistles;chana;rice||0|
g|she doesn't want a party this year she just wants a quiet dinner with family, nothing big|||party;this year;quiet dinner;family;nothing big||2|
e|hi oscar the new hire starts on monday and her laptop isn't set up yet can you sort it thanks wren|||Oscar;new hire;Monday;laptop;yet;Wren||1|
eh|hi felix the deadline is probably going to slip a few days since the designs came in late sorry about that thanks clara|||Felix;deadline;probably;slip;designs;late;Clara||0|apology was dictated
ea|hi leo we can do the review either tuesday at ten or thursday at three let me know which one works thanks ivy||10/ten;3/three|Leo;review;Tuesday;Thursday;Ivy||0|alternative: both slots kept
en|hello mrs iyer your son's fees of eighteen thousand four hundred are pending for the second term kindly pay by the tenth regards accounts team|18,400/18400|10th/tenth|Iyer;fees;pending;second term;accounts team||0|
e|hi rosa the photos from the shoot are ready i've uploaded around eighty edited ones to the folder thanks theo|80||Rosa;photos;shoot;edited;folder;Theo;around||0|
ei|hi team please note the review has been preponed to wednesday eleven am so kindly prepare accordingly thanks manager|11||team;review;preponed;Wednesday;prepare accordingly||0|
l|so the menu for saturday starters are paneer tikka and corn soup mains are biryani and dal and dessert is gulab jamun|||Saturday;paneer tikka;corn soup;biryani;dal;gulab jamun||0|
l|things to discuss with the contractor the timeline the payment schedule the warranty and who handles the permits|||contractor;timeline;payment schedule;warranty;permits||0|
ln|the kids' activities are swimming on monday at four piano on wednesday at five thirty and football on saturday at nine|5:30|4/four;9/nine|swimming;Monday;piano;Wednesday;football;Saturday||0|
l|questions for the landlord is the deposit refundable who pays for repairs and can we have a pet|||deposit;refundable;repairs;pet||0|questions should stay questions
lg|for the presentation slides don't use red text don't add animations and keep it under fifteen slides|15||slides;red text;animations||2|
q|so is it okay if i bring a plus one to the farewell or is it just the team|||plus one;farewell;team||0|question stays a question
n|the fridge has been making noise since the twelfth and the warranty expires on the thirty first||12th/twelfth;31st/thirty-first|fridge;noise;warranty||0|
g|um i don't want to cancel the plan i just want to pause it for two months while i'm travelling||2/two|cancel;pause;travelling||1|
h|my guess is the package is stuck at customs, it usually takes like a week but this is almost three||3/three|guess;package;customs;usually;week;almost||0|hedges kept
c|tell mum i'll call her at eight no make it nine because the match ends late|9||mum;call;match ends late|8|0|correction: 9 not 8
i|you can drop the documents at my office, the watchman knows, just give my name at the gate itself|||documents;office;watchman;my name;gate;itself||0|
t|the cache key is user colon id colon profile and it expires after ten minutes in redis||10/ten|cache key;Redis;expires||0|
p|okay so here's the address new line flat four oh two new line green park towers new line pune|402||Green Park Towers;Pune|new line|0|
n|we need about two point five metres of fabric for the curtains and it's three hundred and twenty a metre|2.5;320||fabric;curtains;metre;about||0|
a|the lecture is in hall a or hall b, the email said one and the app says the other|||lecture;hall A;hall B;email;app||0|alternative: both halls kept
g|nobody told me the meeting was cancelled, i waited for half an hour|||meeting;cancelled;half an hour||1|
h|i might go for the evening show instead if the earlier one sells out|||might;evening show;if;sells out||0|condition kept
c|the kickoff call is at eleven thirty india time sorry eleven thirty singapore time|11:30||kickoff call;Singapore time|India time|0|correction: Singapore time
i|actually i was out of station last week that's why i couldn't revert on your mail|||out of station;last week;revert;mail||1|
e|hi maya um the bikes are booked for both days and the guide meets us at the hostel at eight thanks peter||8/eight|Maya;bikes;both days;guide;hostel;Peter||0|
eg|hi mohan the replacement part hasn't arrived and the technician can't come until it does please update me thanks alok|||Mohan;replacement part;technician;until;Alok||2|

# ---- MEDIUM rows part C ----
g|so the bank says the cheque hasn't cleared and they won't tell me why over the phone, i have to visit the branch|||bank;cheque;cleared;over the phone;branch||2|
c|the cake order is for saturday the nineteenth no hold on sunday the twentieth at noon|20||cake order;Sunday;noon|Saturday;19|0|correction: Sunday the 20th
h|the forecast says there's a seventy percent chance of rain so the match might get called off|70||forecast;chance of rain;match;might||0|
q|um before i sign up do you know whether the course certificate is accepted by employers or is it just for learning|||course certificate;employers;just for learning||0|question stays a question
i|i told the dhobi to come on tuesday but he came today itself and took all the shirts|||dhobi;Tuesday;today itself;shirts||0|
t|so the pull request number four eighty two changes the auth middleware and needs two approvals before merging|482|2/two|pull request;auth middleware;approvals;merging||0|
a|for the gift we could get the headphones or the smartwatch, i'm fine with either honestly|||gift;headphones;smartwatch;either||0|alternative: both kept
n|my sleep score was sixty eight last night and i only got five hours twenty minutes|68|5 hours 20/five hours twenty/5 hours and 20|sleep score;last night;only||0|
g|i'm never ordering from that place again, the food was cold and they didn't include the cutlery|||never;food was cold;cutlery||2|
p|um meeting notes colon decided to hire two designers full stop budget approved full stop||2/two|meeting notes;hire;designers;budget approved|full stop|0|
e|hi isla um can you send me the slides from yesterday's session i missed the last part thanks owen|||Isla;slides;yesterday;missed;Owen||0|
eh|hi jonas the team thinks we can probably ship the update next week assuming the tests pass thanks freya|||Jonas;probably;ship;next week;assuming;tests pass;Freya||0|condition kept
en|hi zoe the parking pass costs sixty five a month and you can pick it up from reception after three thanks noah|65|3/three|Zoe;parking pass;reception;Noah||0|
ec|hi amara the board meeting is on the sixth sorry the seventh at the head office thanks kwame||7th/seventh|Amara;board meeting;head office;Kwame|6th;sixth|0|correction: 7th, not 6th
ei|hi neha please find attached the PG agreement, the deposit is two months rent and kindly sign and send back by monday thanks vikram||2/two|Neha;PG agreement;deposit;Monday;Vikram||0|
eg|dear mr shah we regret that we cannot extend the offer deadline beyond friday regards hr team|||Shah;cannot;offer deadline;Friday;HR team||1|
l|errands for tomorrow return the gym bag no sorry return the borrowed drill, buy stamps, and get the car washed|||borrowed drill;stamps;car washed|gym bag|0|correction: borrowed drill, not gym bag
l|okay the shortlist for the flat is the one in koramangala the one near the metro and the one with the big balcony|||shortlist;Koramangala;metro;big balcony||0|
ln|workout today was three sets of squats ten push ups twenty lunges and a two kilometre run|20|3/three;10/ten;2/two|squats;push;lunges;run||0|
lq|things i need to ask the vet is the rash serious does she need a cone and when is the next vaccine|||vet;rash;cone;vaccine||0|
lt|services to restart are nginx the auth service the queue worker and the cron scheduler|||nginx;auth service;queue worker;cron scheduler||0|
li|for the trip to manali we need woollens, thermals, a good jacket and some dry fruits from home|||Manali;woollens;thermals;jacket;dry fruits||0|
g|the dishwasher isn't draining and the repair guy says it's not under warranty anymore|||dishwasher;draining;repair guy;warranty;anymore||2|
h|it seems like the app crashes only when you rotate the phone but i haven't tested it on android yet|||app crashes;only;rotate;Android;yet;seems like||1|
c|we land in dubai at four am local no wait four pm local and the layover is three hours|4|3/three|Dubai;layover;local||0|correction: 4 p.m., not 4 a.m.
q|is anyone else getting charged twice for the subscription or is it just me|||charged twice;subscription;just me||0|question stays a question
i|ma'am the courier boy came but nobody was at home so he left the parcel with the neighbour aunty|||courier;nobody;parcel;neighbour aunty||1|
t|the json payload has three fields name email and plan where plan is either free or pro||3/three|JSON;name;email;plan;free;pro||0|alternative free or pro kept
a|i'll either take leave on the twenty fourth or work half day, haven't decided||24th/twenty-fourth|leave;half day;decided||1|alternative: leave or half day both kept
p|so the title is comma quote building better habits unquote comma and the subtitle is still pending|||Building Better Habits;subtitle;pending|unquote|0|
g|i didn't say we'd cover the travel costs, i said we'd look into it|||travel costs;look into it||1|
h|i'd probably go with the cheaper option unless the reviews are terrible|||probably;cheaper option;unless;reviews||0|condition kept
n|the bus pass costs twelve hundred for the month or four hundred fifty for a week|1,200/1200;450||bus pass;month;week||0|
c|the guest speaker is doctor fernandes oh sorry doctor fonseca from the university|||Fonseca;guest speaker;university|Fernandes|0|correction: Fonseca
e|hi tara thanks for hosting last night the food was amazing and the kids had a blast cheers max|||Tara;hosting;last night;food;kids;Max||0|
eq|hi marco when you get a chance could you review the draft contract before thursday thanks lena|||Marco;draft contract;Thursday;Lena||0|request stays a question
en|hi ethan the quote for the six laptops is four lakh twenty thousand including tax thanks chloe||4,20,000/420,000/420000/4.2 lakh/4 lakh 20;6/six|Ethan;quote;laptops;tax;Chloe||0|
e|hi peter we've moved the team lunch to the rooftop place since the old one is closed for renovation thanks olivia|||Peter;team lunch;rooftop;closed;renovation;Olivia||0|
l|before leaving switch off the geyser lock the balcony door and give the spare key to the security guard|||geyser;balcony door;spare key;security guard||0|
ln|the order was two chicken burgers one veg wrap three fries and a large coke|||chicken burgers;veg wrap;fries;large coke||0|
lc|invite ananya, bea, and oscar uh scratch oscar, he said he can't make it|||Ananya;Bea||0|correction: Oscar dropped; reason kept
l|weekend plan clean the balcony finish the puzzle and call grandma|||balcony;puzzle;grandma||0|
g|we couldn't get tickets for the late show and the early one doesn't work for kabir|||tickets;late show;early one;Kabir||2|
i|tell the driver to take the service road, the main road is jam packed at this time|||driver;service road;main road;jam packed||0|
t|run pytest with the dash k flag and the test name to only run the failing one|||pytest;only;failing||0|
h|we should hopefully hear back from the visa office by the end of the month|||hopefully;visa office;end of the month||0|
c|the pickup is at the north entrance oh wait it's the east entrance, north is closed|||pickup;east entrance;closed||0|correction: east entrance; north mentioned only as closed
n|i lost three point two kilos this month and my goal is another four by december|3.2|4/four|lost;goal;December||0|
p|so excited for the trip exclamation mark can't wait to see everyone|||excited;trip;see everyone|exclamation mark|1|
g|please don't call after ten, the baby's asleep and the doorbell doesn't work either||10/ten|call;baby;doorbell;either||2|
a|we can paint the room sage or that pale blue, both match the curtains|||sage;pale blue;both;curtains||0|alternative kept
e|hi bilal the hackathon starts at nine on saturday and lunch will be provided so don't bring food thanks sana||9/nine|Bilal;hackathon;Saturday;lunch;Sana||1|
ea|hi yusuf the parts will cost either nine hundred or eleven hundred depending on the model thanks farhan|900|1,100/1100|Yusuf;parts;depending on the model;Farhan||0|alternative: both prices kept

# ---- LONG rows part A (50-120 words) ----
n|okay so um quick update on the move the packers are coming on friday at eight am and they said it'll take about five hours, the truck is booked for two pm and the total quote was twenty two thousand five hundred which includes insurance, uh we still need to pay the advance of five thousand by wednesday and the rest on delivery, also the new place gets the keys on thursday evening so we can drop some boxes there before|22,500/22500;5,000/5000|8/eight;2/two;5/five|packers;Friday;truck;insurance;advance;Wednesday;on delivery;keys;Thursday evening;about||0|facts: packers Fri 8 a.m. ~5 hrs; truck 2 p.m.; quote 22,500 incl insurance; advance 5,000 by Wed; keys Thu evening
g|so i talked to the clinic about the test results and um they said nothing looks serious but they don't want to rule anything out yet, i'm not supposed to lift anything heavy for two weeks and i shouldn't skip the physio sessions, they also said not to take the painkillers on an empty stomach, and uh i can't drive until the follow up which is on the twenty first||21st/twenty-first;2/two|clinic;test results;nothing;rule anything out;yet;lift anything heavy;physio;painkillers;empty stomach;drive;follow-up/follow up||6|facts: six negations; 2 weeks; follow-up on the 21st
c|right so for the reunion we're meeting at the old canteen at six, no wait they changed it, it's at the community centre on mg road now, and it starts at seven not six, uh each person is chipping in fifteen hundred which covers dinner and the hall, and sameer is handling the music, sorry not sameer, nikhil is doing music and sameer does the photos|1,500/1500|7/seven|reunion;community centre/community center;MG Road;dinner;Nikhil;music;Sameer;photos|canteen|1|corrections: community centre (not canteen), 7 (not 6), Nikhil does music, Sameer photos
h|i've been thinking about the job offer and um i think i'm leaning towards accepting it but i might ask for a slightly higher base first, maybe around ten percent more, if they say no i'll probably still take it because the team seemed great, but i'm not completely sure about the commute, it could be an hour each way on bad days|10||job offer;I think;leaning;might;base;maybe;around;if they say no;probably;team;commute;could;each way||2|hedges and condition kept; ~10% more
i|so yaar the plan for sunday is like this, we'll leave by six in the morning itself to avoid traffic, stop for breakfast at that famous dhaba on the highway, reach lonavala by ten and then go to the waterfall, mummy said we have to be back by eight in the evening because papa has office on monday, so no late night drive this time||6/six;10/ten;8/eight|yaar;Sunday;morning itself;traffic;dhaba;highway;Lonavala;waterfall;mummy;papa;office;Monday;late night drive||1|
t|okay so the issue with the login flow is um when the user signs in with google the callback goes to slash auth slash callback but the redirect uri in the console is set to the old domain old dot example dot com, so we need to update it to app dot example dot com and also clear the session cookie because it's still scoped to the old domain, after that run the e2e suite again, it takes like twelve minutes|12||login flow;Google;callback;redirect URI;app;example;session cookie;still;old domain;e2e suite||0|
q|so i had a few questions about the lease renewal um first does the rent increase apply from the start of the next term or from the date we sign, second are we allowed to sublet the spare room for a couple of months, and third if we break the lease early what's the penalty because my contract at work might not get extended|||lease renewal;rent increase;next term;sublet;spare room;break the lease;penalty;might;contract;extended||1|three questions must stay questions; not answered
p|okay dictating the note now, dear neighbours comma we're having a small get together on saturday evening from six to ten full stop there might be some music comma but we'll keep it down after nine full stop if anything bothers you comma just knock on flat three b full stop thanks for understanding exclamation mark||6/six;10/ten;9/nine|neighbours;get-together/get together;Saturday evening;might;music;if anything bothers you;3B/3 B|comma;full stop;exclamation mark|0|spoken punctuation converted; times kept
n|um so the household budget for this month, rent is twenty eight thousand, groceries around nine thousand, electricity was two thousand three hundred and forty, the internet is nine ninety nine, and we spent about six thousand on eating out which is way too much, so total comes to roughly forty six and a half thousand, next month i want to cut the eating out to three thousand|28,000/28000;2,340/2340;999|9,000/9000;6,000/6000;46,500/46500/46.5 thousand;3,000/3000|rent;groceries;electricity;internet;eating out;roughly;next month||0|
a|for the team offsite we have two options really, either the resort near the lake which is two nights for about eighteen thousand per head, or the city hotel which is just one night but only nine thousand per head, uh the lake one has better activities but the hotel is easier for people with kids, we can also do a vote, i'm honestly fine with either|18,000/18000;9,000/9000|2/two|offsite;resort;lake;city hotel;one night;per head;activities;kids;vote;either||0|alternative: both options and prices kept
e|hi joel um so following up on our call yesterday i've shared the updated design files in the drive folder and the main changes are the new colour palette the simplified checkout and the bigger buttons on mobile, uh i haven't touched the onboarding screens yet because we're still waiting on the copy from marketing, could you take a look before thursday and leave comments directly in the file, thanks a lot ruth|||Joel;call yesterday;design files;colour palette/color palette;checkout;buttons;mobile;onboarding;yet;marketing;Thursday;comments;Ruth||1|
eg|hello mr kapoor i wanted to inform you that unfortunately we won't be able to deliver the full order by the fifteenth as planned, the supplier hasn't shipped the second batch of fabric and they can't give a firm date yet, we can send the first two hundred units on time and the remaining three hundred within ten days after, please let me know if that works for you regards simran|200;300|15th/fifteenth;10/ten|Kapoor;full order;supplier;second batch;fabric;firm date;first;remaining;on time;Simran||3|split delivery 200 then 300
ec|hi tanvi so the workshop is confirmed for the twelfth at the innovation hub, uh it runs from ten to four with lunch at one, we have twenty five seats, sorry thirty five seats, and so far twenty eight people have registered, could you send a reminder to everyone on the tenth and also check if the projector there supports hdmi thanks kabir|35;28|12th/twelfth;10th/tenth;10/ten;4/four;1/one|Tanvi;workshop;Innovation Hub;lunch;registered;reminder;projector;HDMI;Kabir|25|0|correction: 35 seats, not 25
ei|dear sir with reference to your mail dated the third i would like to inform you that the payment of one lakh twenty thousand has been released from our side today itself, kindly check and confirm receipt, also please do the needful regarding the pending invoice for september as the audit is next week, thanks and regards accounts department||3rd/third;1,20,000/120,000/120000/1.2 lakh/1 lakh 20|sir;mail;payment;released;today itself;confirm receipt;do the needful;pending invoice;September;audit;next week;accounts department||0|
eh|hi olivia hope you're well um i wanted to check whether the proposal i sent last week reached you, i think it may have gone to spam because i didn't get the usual read receipt, the budget section is probably the part that needs the most discussion, if it's easier we could go through it on a quick call sometime next week, thanks tom|||Olivia;proposal;last week;I think;may have gone to spam;read receipt;budget section;probably;if;quick call;next week;Tom||1|
l|so for the new apartment we still need to buy a few things, um a mattress for the guest room, a shoe rack, curtains for the living room, a microwave, and a decent office chair because my back is killing me, uh oh and some plants for the balcony, maybe two or three small ones|||mattress;guest room;shoe rack;curtains;living room;microwave;office chair;plants;balcony;maybe||0|2/two or 3/three plants kept
lt|okay the checklist before we go live is um make sure the ssl cert is valid, point the dns to the new load balancer, run the database migration on a snapshot first, warm up the cache, turn on the monitoring alerts, and keep the old servers running for at least forty eight hours in case we need to roll back|48||SSL;DNS;load balancer;migration;snapshot;cache;monitoring alerts;old servers;at least;roll back||0|
ln|so the conference schedule for day one is registration at eight thirty keynote at nine fifteen the panel on ai safety at eleven lunch at twelve thirty and then workshops from two to five, the dinner is at seven thirty at the rooftop restaurant|8:30;9:15;12:30;7:30|11/eleven;2/two;5/five|registration;keynote;panel;AI safety;lunch;workshops;dinner;rooftop restaurant||0|
lc|okay the people on the committee are going to be anita for finance, joel for events, sana for outreach, and uh owen for the newsletter, wait no owen said he's too busy, so maya will do the newsletter, and i'll be the coordinator|||committee;Anita;finance;Joel;events;Sana;outreach;Maya;newsletter;coordinator||0|correction: Maya does newsletter; Owen only as too busy
li|for the housewarming puja on sunday we need to arrange, uh, the pandit ji for nine am, flowers and garlands, sweets for around fifty people, chairs from the tent house, and lunch from the caterer near the station, please also call masi and tell her the timing|50|9/nine|housewarming;puja;Sunday;pandit ji;flowers;garlands;sweets;around;chairs;tent house;lunch;caterer;masi;timing||0|
n|so the results from the survey are in, we got four hundred and twelve responses which is about thirty percent of the user base, sixty one percent said they'd pay for the premium tier, the most requested feature was offline mode with a hundred and forty votes, and the average satisfaction score was seven point eight out of ten|412;30;61;140;7.8|10/ten|survey;responses;about;user base;premium tier;offline mode;votes;satisfaction score||0|
g|um i need to vent a bit, so the contractor promised the kitchen would be done by last friday and it's still not finished, the tiles don't match what we picked, nobody showed up on monday, and when i called he didn't even apologise, i'm not paying the final instalment until it's fixed and i don't want him back for the bathroom|||contractor;kitchen;last Friday;still;tiles;picked;Monday;apologise/apologize;final instalment/final installment;until;bathroom||6|
c|reminder for next week, monday i have the performance review at ten, tuesday is the client demo at three, wait no the demo moved to wednesday at three, and thursday i'm on leave, friday is just the usual standup and then the team lunch at one thirty, oh and the review is at eleven not ten|1:30|3/three;11/eleven|Monday;Wednesday;client demo;Thursday;leave;Friday;standup;team lunch;performance review|Tuesday is the client demo;10|0|corrections: demo Wed 3; review at 11 not 10
h|i looked at the second hand car and honestly it seems okay, the engine sounds fine but the tyres might need replacing soon, the seller says it's done around forty thousand kilometres though i'm not sure i believe that, if the mechanic says it's fine i'd probably offer three point two lakh and go up to three and a half at most||40,000/40000;3.2 lakh/3,20,000/320,000;3.5 lakh/3 and a half/3,50,000/350,000|second-hand/second hand;engine;tyres;might;seller;around;not sure;if the mechanic;probably;at most||1|hedges + condition kept; offer 3.2 lakh, max 3.5
q|um so i'm trying to figure out the travel insurance, does the policy cover cancellations if i get sick before the trip, and is there a limit on how much they reimburse for lost baggage, also do i need to buy it before i book the flights or can i add it later|||travel insurance;policy;cancellations;sick;limit;reimburse;lost baggage;book the flights;later||0|questions stay questions; not answered
t|so for the new microservice we're using postgres fifteen with the connection pool set to twenty, the service listens on port eight zero eight one, logs go to stdout in json format, and alerts fire if the p ninety nine latency goes above three hundred milliseconds for more than five minutes, the repo is github dot com slash acme slash billing dash svc|15;20;8081;300|99/p99;5/five|microservice;Postgres;connection pool;port;stdout;JSON;alerts;latency;milliseconds;billing||0|
p|okay so the caption for the post is going to be comma, um, twenty years of friendship and still going strong exclamation mark, new line, thank you all for coming tonight full stop, new line, hashtag reunion hashtag old friends|20||friendship;still going strong;thank you all for coming tonight;reunion|exclamation mark;full stop;new line|0|hashtags dictated
i|actually i wanted to tell you that my exams are getting over on the twentieth so after that i'm totally free, we can plan the trip to rishikesh, but please don't book anything before confirming with papa because he gets tensed if we decide things without asking him first, and see if the rafting is open in november also||20th/twentieth|exams;Rishikesh;don't;papa;tensed;without;rafting;November||2|condition 'before confirming with papa' kept
a|for the anniversary dinner i'm torn between the japanese place downtown which has a tasting menu for about six thousand for two, and the rooftop grill near the river which is cheaper but you need to book three days in advance, both have good reviews so let's decide by tonight||6,000/6000;3/three|anniversary dinner;Japanese place;tasting menu;rooftop grill;river;cheaper;book;in advance;both;tonight||0|alternative: both restaurants kept
e|hi team um just wanted to share a quick summary of today's call, we agreed to move the launch to the second week of november, marketing will prepare the press kit by the twenty fifth, and engineering will freeze features on the first, nobody raised any blockers but we'll revisit the pricing on friday, thanks everyone, paige||25th/twenty-fifth;1st/first|team;summary;launch;second week of November;marketing;press kit;engineering;freeze features;blockers;pricing;Friday;Paige||1|
en|hi uma the final numbers for the charity run are in, we had three hundred and eighty runners, raised one lakh sixty thousand rupees, and around forty volunteers helped out, uh the next run is planned for march so please block your calendar, and thanks again for organising the water stations, cheers bilal|380|1,60,000/160,000/160000/1.6 lakh/1 lakh 60;40|Uma;charity run;runners;raised;around;volunteers;March;water stations;Bilal||0|
e|dear professor nair thank you for agreeing to supervise my project, i've attached the proposal and a rough timeline, um i was hoping we could meet sometime in the first week of next month to discuss the methodology, i'm available on tuesdays and thursdays after two, please let me know what suits you, regards harpreet||2/two|Nair;supervise;project;proposal;rough timeline;first week of next month;methodology;Tuesdays;Thursdays;Harpreet||0|
l|okay so the packing list for the beach holiday is swimsuits, um, two pairs of flip flops, sunscreen spf fifty, a beach towel each, the snorkel gear, a waterproof phone pouch, and the first aid kit, uh don't pack the big camera, the phone is enough|50|2/two|swimsuits;flip-flops/flip flops;sunscreen;SPF;beach towel;snorkel gear;waterproof phone pouch;first aid kit;big camera||1|
g|so the internet provider called back and um they said the outage isn't on their end, there's no fault in the area, and they can't send a technician until monday, i told them we work from home and we can't wait that long but they wouldn't budge, i'm thinking of switching providers but the contract doesn't end till june|||internet provider;outage;fault;technician;Monday;work from home;wait that long;budge;switching providers;contract;June||6|
n|so my running log for the week, monday five k in twenty eight minutes, wednesday intervals eight by four hundred metres, friday an easy seven k, and sunday the long run of eighteen kilometres in one hour fifty two, total distance is around thirty three kilometres which is my highest ever|28;400;18;1:52/1 hour 52;33|5K/5 k/5k/5 km;8/eight;7K/7 k/7k/7 km|running log;Monday;Wednesday;intervals;Friday;Sunday;long run;around;highest||0|
c|so the guest list for the dinner is final now, it's twelve people, no sorry fourteen because tara is bringing her parents, uh the veg count is six and non veg is eight, and one person is allergic to nuts so no cashew in the gravy, the dinner is at eight on saturday|14|6/six;8/eight|guest list;Tara;parents;veg;non-veg/non veg;allergic to nuts;cashew;gravy;Saturday|12|1|correction: 14 not 12; nut allergy constraint

# ---- LONG rows part B ----
h|so about the garden project, i think we could start with the raised beds this weekend if the soil delivery comes on friday, but it might get pushed because the supplier sounded unsure on the phone, worst case we just do the compost bin first, uh the tomatoes probably need to go in by the end of the month otherwise it's too late for this season|||garden project;I think;raised beds;this weekend;if;soil delivery;Friday;might;supplier;unsure;worst case;compost bin;tomatoes;probably;end of the month;otherwise;too late||0|condition + hedges kept
n|um so the electricity board finally replied, the old meter reading was four thousand two hundred and six and the new one is four thousand five hundred and ninety one, so we used three hundred and eighty five units, at seven rupees fifty per unit that's about two thousand eight hundred and eighty eight, plus a fixed charge of a hundred and twenty|4,206/4206;4,591/4591;385;7.50;2,888/2888;120||electricity board;meter reading;units;per unit;about;fixed charge||0|
q|hey so i've been meaning to ask, um, how do you guys manage the shared expenses on trips, do you use an app or just a spreadsheet, and what happens when someone pays for a big thing like the hotel, do you settle up right away or at the end, because last time it got really messy and i don't want that again|||shared expenses;trips;app;spreadsheet;hotel;settle up;at the end;messy;again||1|questions stay questions; not answered
g|uh so i went to the passport office today and they said the address proof isn't valid because it's older than three months, and they won't accept the rental agreement unless it's notarised, so i couldn't submit the application, the next slot isn't available for two weeks, so the trip in december might not happen if this doesn't get sorted|||passport office;address proof;three months/3 months;rental agreement;unless;notarised/notarized;application;next slot;December;might;if||6|
i|hello aunty, this is about the tiffin service, from next week we'll need lunch for three people only instead of four since my brother is going back to hostel, and please make it less spicy for papa, no onion garlic on tuesdays as usual, and we'll pay the monthly amount on the first itself, thank you||3/three;4/four;1st/first|aunty;tiffin service;next week;lunch;instead of;brother;hostel;less spicy;papa;onion;garlic;Tuesdays;monthly amount;itself||1|
t|so the flaky test is test underscore checkout underscore applies underscore coupon, it fails maybe one in ten runs, i think it's a race condition because the coupon service mock resolves after the cart total is calculated, the fix is probably to await the promise in the before each hook, i'll open a ticket called pay dash nine one seven and tag it as flaky|917|10/ten|flaky test;checkout;coupon;maybe;I think;race condition;mock;cart total;probably;await;promise;hook;ticket;PAY||0|
c|so the order from the stationery shop, we need fifty notebooks, two hundred pens, no wait make that one fifty pens, ten staplers, and uh five boxes of a four paper, sorry six boxes because the printer room is out, and please get the bill in the company name not mine|50;150|10/ten;6/six;A4|stationery shop;notebooks;pens;staplers;boxes;paper;printer room;bill;company name|200;5 boxes|1|corrections: 150 pens (not 200), 6 boxes (not 5)
a|for the weekend we could either do the trek on saturday and rest on sunday, or skip the trek and go to the food festival on both days, um the trek is cheaper but it's supposed to rain on saturday, the festival is around eight hundred per person per day, so let's talk about it tonight and pick one|800||weekend;trek;Saturday;Sunday;food festival;both days;cheaper;supposed to rain;around;per person;tonight||0|alternative: both plans kept
p|okay new paragraph the first point is about the timeline comma we're about two weeks behind full stop new paragraph the second point is the budget comma which is still within limits full stop new paragraph and finally comma the client wants a demo before christmas question mark i think that's doable full stop|||first point;timeline;two weeks/2 weeks;behind;second point;budget;still within limits;finally;client;demo;Christmas;doable|new paragraph;comma;full stop;question mark|0|spoken paragraph breaks converted
e|hi lena um thanks for the quick turnaround on the contract, i went through it last night and it mostly looks good, just two things, the payment terms should say thirty days not sixty, and the termination clause needs a notice period, we'd suggest ninety days, once those are fixed i'm happy to sign, thanks marco|30;90|2/two|Lena;contract;last night;payment terms;termination clause;notice period;suggest;once;sign;Marco||1|30 days, not 60; 90-day notice suggested
eq|hi kwame hope your week is going well, um a couple of questions about the event next month, is the venue okay with us bringing our own caterer, do we need to arrange our own security, and can we get access the night before to set up the stage, it would really help to know by friday so we can finalise the vendor list, thanks amara|||Kwame;event;next month;venue;own caterer;security;night before;stage;Friday;vendor list;Amara||0|three questions stay questions
eg|dear ms rao i'm writing regarding my order number eight four two two one, the washing machine was delivered on monday but it hasn't been installed yet and the technician didn't turn up for either of the two appointments, i would like the installation done this week or a full refund, regards pooja|84221|2/two|Rao;order number;washing machine;Monday;installed;yet;technician;installation;this week;full refund;Pooja||2|
ec|hi ishaan quick update, the photographer for the launch event is booked for the eighth, sorry the ninth, from four to eight pm, the fee is twenty five thousand and he'll deliver edited photos within a week, uh can you share the shot list with him by tuesday, thanks devika|25,000/25000|9th/ninth;4/four;8/eight|Ishaan;photographer;launch event;fee;edited photos;within a week;shot list;Tuesday;Devika|8th;eighth|0|correction: 9th, not 8th
ei|hello all, kindly note that the society water supply will be shut on saturday from ten am to four pm for tank cleaning, please store sufficient water in advance, the lift will also be under maintenance on sunday morning so kindly use the stairs, sorry for the inconvenience, regards secretary||10/ten;4/four|society;water supply;shut;Saturday;tank cleaning;store sufficient water;lift;maintenance;Sunday morning;stairs;inconvenience;secretary||0|apology dictated
e|hi freya um so i'm putting together the reading group schedule, we meet every other thursday at seven at my place, the first book is the one about the history of salt, then we'll vote on the next ones, each person brings a snack, please let me know if thursdays don't work for you and i'll try to adjust, cheers jonas||7/seven|Freya;reading group;every other Thursday;my place;first book;history of salt;vote;snack;if;adjust;Jonas||1|
l|so the agenda for the parent teacher sorry the parent coach meeting is, one, the season schedule, two, the uniform costs, three, the carpool roster, and four, the end of season party, we'll keep it to forty five minutes max|45||agenda;parent coach meeting;season schedule;uniform costs;carpool roster;end of season party/end-of-season party;max|parent teacher|0|correction: parent coach meeting
ln|um the dosage the doctor gave is, the antibiotic twice a day after meals for five days, the antacid once in the morning before breakfast, the cough syrup ten ml at night, and the vitamin d sachet once a week on sundays for eight weeks|10|5/five;8/eight|dosage;doctor;antibiotic;twice a day;after meals;antacid;before breakfast;cough syrup;ml;at night;vitamin D;once a week;Sundays||0|
lh|ideas for the team building day, maybe an escape room in the morning, a cooking class if we can find one that takes twenty people, a picnic in the park, and possibly a karaoke evening, though some people might not like karaoke, let's see what the poll says|20||team building;maybe;escape room;cooking class;if;picnic;park;possibly;karaoke;might;poll||1|
lg|the house rules for the guests are, no shoes inside the bedrooms, no smoking anywhere including the balcony, quiet hours after ten thirty, and please don't leave food out because of the ants, also the wifi is guest house two four and the password is on the fridge|10:30|24/two four|house rules;guests;shoes;bedrooms;smoking;balcony;quiet hours;food;ants;wifi;password;fridge||3|
li|for the office diwali party we need, um, a dj from seven to eleven, snacks and mithai for around eighty people, the rangoli competition at six, secret santa gifts under five hundred rupees, and someone to handle the photo booth, kindly send your names if you want to volunteer|500|7/seven;11/eleven;80;6/six|Diwali party;DJ;snacks;mithai;around;rangoli competition;secret santa;gifts;under;photo booth;volunteer||0|
n|so the car loan details, the principal is six lakh, the interest rate is eight point nine percent, the tenure is five years, which makes the emi around twelve thousand four hundred, and there's a processing fee of one percent plus gst, the first emi is due on the fifth of next month|8.9|6 lakh/6,00,000/600,000/600000;12,400/12400;5/five;1/one;5th/fifth|car loan;principal;interest rate;tenure;EMI;around;processing fee;GST;next month||0|
c|okay so for the swap meet, we're setting up at the north parking lot from eight, hmm no it's the south lot because north is being resurfaced, each table costs two hundred, uh sellers keep everything they make, and the organisers take nothing, we already have twenty two tables booked, sorry twenty four|200;24|8/eight|swap meet;south lot;resurfaced;table;sellers;organisers/organizers;nothing;booked|22|1|corrections: south lot, 24 tables
h|apparently the new metro line opens in january, though they've said that before, if it actually happens my commute drops from an hour and a half to maybe forty minutes, which would be huge, i might even sell the car at that point but let's not get ahead of ourselves|40||apparently;metro line;January;if;commute;an hour and a half/1.5 hours/90 minutes;maybe;might;sell the car;let's not||1|
q|um so the landlord sent the new agreement and i wanted to check a couple of things, is the security deposit still two months or did they increase it, are we allowed to paint the walls, and is the maintenance included in the rent or separate, also when exactly does the lock in period end||2/two;lock-in/lock in|landlord;new agreement;security deposit;still;paint the walls;maintenance;rent;separate||0|questions stay questions
g|i don't really want to go to the party on friday, not because of anyone there, i'm just exhausted and haven't had a quiet evening in weeks, i'll text kiran that i can't make it but i don't want her to think i'm upset|||party;Friday;anyone;exhausted;quiet evening;weeks;text;Kiran;upset||5|
t|so the s three bucket for uploads is named acme dash user dash uploads dash prod, the lifecycle rule moves objects to glacier after ninety days and deletes them after three sixty five, we should not make the bucket public, and the presigned urls expire in fifteen minutes|90;365;15||S3/S 3/s three;bucket;uploads;lifecycle rule;Glacier;deletes;public;presigned URLs;expire||1|
n|so my mutual fund statement says the total invested is three lakh forty thousand and the current value is three lakh ninety one thousand, so the gain is about fifty one thousand or roughly fifteen percent, the sip of five thousand goes out on the seventh every month|15|3,40,000/340,000/340000/3.4 lakh/3 lakh 40;3,91,000/391,000/391000/3.91 lakh/3 lakh 91;51,000/51000;5,000/5000;7th/seventh|mutual fund;total invested;current value;gain;about;roughly;SIP;every month||0|
a|um for the logo the client liked two directions, the minimal one with just the initials in navy, or the badge style with the mountain icon in green, they said they'd be happy with either but want to see both on the website mockup before they decide, so let's prepare both by thursday|||logo;client;minimal;initials;navy;badge;mountain icon;green;either;both;website mockup;Thursday||0|alternative: both directions kept
i|good morning sir, i am writing to request leave from the twenty third to the twenty seventh as my sister's engagement is happening in jaipur, i have completed the pending reports and kabir has agreed to handle my tickets during this period, kindly approve the same||23rd/twenty-third;27th/twenty-seventh|good morning;sir;leave;sister's engagement;Jaipur;pending reports;Kabir;tickets;kindly approve||0|
p|write this down, the wifi name is home underscore net underscore five g and the password is all caps blue sky then the number seven two nine then exclamation mark, the router is behind the tv if you need to restart it|729||wifi;password;router;TV;restart|exclamation mark|0|password literal reconstructed; 729 kept
e|hi team just a heads up that i'll be on leave from monday to wednesday next week, uh owen will cover the client calls, the weekly report will go out on thursday instead of monday, and if anything urgent comes up you can reach me on my phone, otherwise i'll catch up when i'm back, thanks wren|||team;leave;Monday;Wednesday;next week;Owen;client calls;weekly report;Thursday;instead of;urgent;phone;otherwise;Wren||0|condition kept
eh|hi nora so i spoke to the vendor and it looks like the furniture might arrive a week late, they're blaming the port delays, i've asked them to confirm by tuesday, if it doesn't arrive before the twentieth we may have to rent some tables for the event, i'll keep you posted, thanks hugo||20th/twentieth|Nora;vendor;furniture;might;a week late;port delays;Tuesday;if;may;rent;tables;event;Hugo||1|
en|hi sneha quick numbers for the board deck, revenue for the quarter was two point four crore, up eighteen percent, the gross margin was forty one percent, we added three hundred and twelve customers and churn was under two percent, the cash runway is fourteen months, thanks alok|18;41;312;14|2.4 crore/2,40,00,000;2/two|Sneha;board deck;revenue;quarter;gross margin;customers;churn;under;cash runway;months;Alok||0|
l|so the rotation for the cleaning is, kabir does the kitchen on mondays and thursdays, tanvi does the bathrooms on tuesdays, i take the living room on wednesdays and saturdays, and the trash goes out every evening by whoever is home first, nobody skips without swapping|||rotation;cleaning;Kabir;kitchen;Mondays;Thursdays;Tanvi;bathrooms;Tuesdays;living room;Wednesdays;Saturdays;trash;every evening;swapping||1|
lc|for the camping weekend the cars are, my car takes joel tara and the tents, maya's car takes ben and the food, uh and owen drives the third car with the kayaks, wait no the kayaks go on the roof of my car, owen just takes the chairs|||camping weekend;Joel;Tara;tents;Maya;Ben;food;Owen;third car;kayaks;roof;chairs||0|correction: kayaks on the roof of my car; Owen takes chairs
g|so i called customer care about the double charge and um they said it's not a bug on their side and they can't reverse it without a dispute form, i don't have the original receipt anymore so i'm not sure what to do, maybe the bank statement works|||customer care;double charge;bug;reverse;dispute form;original receipt;anymore;not sure;maybe;bank statement||5|
h|i'm thinking we host the book launch at the art gallery, it should fit around a hundred people, although if more than that rsvp we might need the bigger hall across the street, the gallery quoted forty thousand which seems fair, i'll probably confirm by the end of the week unless someone objects|100;40,000/40000||book launch;art gallery;around;if;RSVP;might;bigger hall;fair;probably;end of the week;unless||0|condition + hedges kept

# ---- part 8: extra long rows, lists, corrections, Indian English ----
lic|okay so for the navratri garba night at the society we need, um, the dj booked from eight to twelve, sorry eight to eleven thirty because of the noise rule, dandiya sticks for around a hundred people, prasad and snacks, and two volunteers at the gate to check passes, kindly confirm your names by thursday yaar|11:30|8/eight;2/two|Navratri;garba;society;DJ;noise rule;dandiya sticks;around;prasad;snacks;volunteers;gate;passes;Thursday;yaar|twelve;12|0|correction: DJ until 11:30, not 12
lc|the shopping list for the week is, uh, oats, two litres of milk, spinach, chicken, no wait make it paneer because we're doing veg this week, a dozen eggs, and the dishwasher tablets, oh and coffee, the dark roast not the medium one|||oats;milk;spinach;paneer;veg this week;eggs;dishwasher tablets;coffee;dark roast|chicken|1|correction: paneer replaces chicken; 2 litres; dozen eggs
lic|for the office move on saturday the packing is, um, each person packs their own desk, the it team does the servers and printers, admin handles the pantry, and the files go with ravish, sorry not ravish, with mohan, the trucks come at seven sharp so please be there by six thirty only|6:30|7/seven|office move;Saturday;own desk;IT team;servers;printers;admin;pantry;files;Mohan;trucks;sharp;only|Ravish|0|correction: Mohan, not Ravish
ln|so the medicine schedule for dad from tomorrow, the bp tablet at eight am, the sugar tablet before lunch and before dinner, the eye drops three times a day, and the calcium at bedtime, and his checkup is on the fourth at eleven thirty|11:30|8/eight;3/three;4th/fourth|medicine schedule;dad;BP tablet;sugar tablet;before lunch;before dinner;eye drops;calcium;bedtime;checkup||0|
lp|okay dictate the list colon number one comma confirm the caterer full stop number two comma send the invites full stop number three comma book the sound system full stop number four comma buy return gifts full stop|||caterer;invites;sound system;return gifts|comma;full stop;colon|0|spoken numbering + punctuation converted
lh|so the possible names for the podcast are, maybe, the slow lane, second draft, or the honest hour, i'm leaning towards second draft but if the domain is taken we'll probably go with the honest hour, and the slow lane is the backup|||podcast;maybe;The Slow Lane;Second Draft;The Honest Hour;leaning;if;domain;probably;backup||0|three names kept; condition kept
lg|for the new intern's first week, um, give her the laptop on monday, walk her through the codebase on tuesday, pair her with joel on wednesday and thursday, and don't assign any production tickets until the second week, also she doesn't have admin access yet, so no deploys|||intern;first week;laptop;Monday;codebase;Tuesday;Joel;Wednesday;Thursday;production tickets;until;second week;admin access;yet;deploys||3|
lt|so the ports are, the frontend on three thousand, the api on eight thousand, postgres on five four three two, and redis on six three seven nine, and the admin panel is on eight thousand one, don't expose any of these publicly except the frontend|3000/3,000;8000/8,000;5432;6379;8001||ports;frontend;API;Postgres;Redis;admin panel;publicly;except||1|
li|okay so for nani's birthday on sunday we're doing, um, a small puja in the morning, lunch at home for the family only, a cake in the evening, and the cousins are making a video, mama is coming from indore and masi will join on video call, keep it a surprise yaar|||nani;birthday;Sunday;puja;lunch;family only;cake;evening;cousins;video;mama;Indore;masi;video call;surprise;yaar||0|
lc|the order of speakers tomorrow is, first the welcome by zoya, then kabir with the product update, then the customer story, uh then the q and a, wait the q and a should be last, so the awards come before the q and a, and we wrap up by five thirty|5:30||speakers;tomorrow;welcome;Zoya;Kabir;product update;customer story;awards;Q&A/Q and A/Q & A;wrap up||0|correction: awards before Q&A; Q&A last
l|for the bathroom renovation we've picked, uh, matte black fittings, the grey hexagon tiles for the floor, a glass partition instead of the curtain, and the wall hung toilet, the vanity is still undecided|||bathroom renovation;matte black fittings;grey hexagon tiles;glass partition;instead of;wall-hung/wall hung;vanity;still undecided||0|
ln|the stats from the hackathon, a hundred and twenty participants, thirty one teams, eighteen projects submitted, and the winning team built a tool for tracking water usage, the prize money was fifty thousand split across three teams|120;31;18|50,000/50000;3/three|hackathon;participants;teams;projects submitted;winning team;water usage;prize money||0|
ic|bhai listen, the match tickets are for saturday, no no, sunday evening, at the wankhede, gates open at five, and the match starts at seven thirty, i've paid two thousand per ticket so just send me the amount whenever, no hurry yaar|7:30|5/five;2,000/2000|match tickets;Sunday evening;Wankhede;gates open;per ticket;whenever;no hurry;yaar|Saturday|1|correction: Sunday evening, not Saturday
ic|accha listen the painter, i mean the carpenter, sorry the electrician, is coming tomorrow at ten for the geyser, so someone has to be home till twelve at least, mummy is going to the temple so you stay back na||10/ten;12/twelve|electrician;tomorrow;geyser;home;at least;mummy;temple;stay back|carpenter;painter|0|correction chain resolves to electrician; 10 / 12 kept
ich|so regarding the loan, the bank said around eight point five percent, actually no it's eight point seven five for salaried people, and the processing will take like ten working days, they need salary slips for three months and form sixteen, i'll submit everything by friday hopefully|8.75|10/ten;3/three;16/sixteen|loan;bank;salaried;processing;working days;salary slips;Form;Friday;hopefully|8.5|0|correction: 8.75%, not 8.5%
i|dear all, please note that the canteen timings have changed from today itself, lunch will be served from twelve thirty to two thirty and tea from four to four thirty, kindly cooperate, regards admin|12:30;2:30;4:30|4/four|canteen timings;today itself;lunch;tea;kindly cooperate;admin||0|
ip|sir comma as discussed comma i have shared the revised estimate full stop the total comes to rupees three lakh seventy five thousand full stop kindly approve at the earliest full stop||3,75,000/375,000/375000/3.75 lakh/3 lakh 75|sir;as discussed;revised estimate;total;kindly approve;at the earliest|comma;full stop|0|
i|arre yaar the internet is down since morning and the jio guy said he'll come only after four, so i'll work from the co working space today, ping me on whatsapp if anything is urgent||4/four|yaar;internet is down;since morning;Jio;only after;co-working/coworking/co working;today;WhatsApp;urgent||0|
ic|we have to submit the assignment by the fifteenth, no actually ma'am extended it to the eighteenth, so we have the weekend also, but don't leave it till the last day like last time yaar||18th/eighteenth|assignment;ma'am;extended;weekend;last day;last time;yaar|15th;fifteenth|1|correction: deadline 18th, not 15th
ic|book two tickets for the eleven am show, sorry one pm show, at the pvr near the mall, and get the recliner seats if they're available, otherwise regular is fine||2/two;1/one|tickets;PVR;mall;recliner seats;if;otherwise;regular|11|0|correction: 1 p.m. show, not 11 a.m.
c|so the dimensions for the bookshelf are a hundred and eighty tall, sixty wide, uh no wait seventy wide, and thirty deep, all in centimetres, and the wood should be walnut, not oak|180;70;30||bookshelf;tall;wide;deep;centimetres/centimeters;walnut;oak|60|1|correction: 70 wide, not 60; walnut not oak
c|tell the photographer the shoot is at the beach at sunrise, so five forty five, scratch that, sunrise is six ten this week, so let's say six||6:10/6.10;6/six|photographer;shoot;beach;sunrise;this week|5:45|0|correction: shoot at 6; sunrise 6:10
c|the agenda item about the bonus is off, i mean it's on, it's just moved to the end, sorry that was confusing|||agenda item;bonus;moved;end;confusing||0|correction: bonus item is on, moved to end
c|my new address is flat twenty one, building c, wait it's building d, palm meadows, whitefield, and the pin code is five six zero zero six six|21;560066||Palm Meadows;Whitefield;pin code;building D|building C|0|correction: building D, not C
c|we're meeting at four, hmm no at half past four, near the fountain in the square, not the one near the station||4:30/half past four|fountain;square;station|4:00|1|correction: half past four
ch|i think we spent about forty thousand on the trip, actually it's closer to forty five once you add the flights, so maybe fifteen thousand each, give or take||45/45,000;15/15,000|I think;trip;closer to;flights;maybe;each;give or take|40;40,000|0|correction: closer to 45 thousand
e|hi clara um so i've finished the first pass on the report, the numbers look fine but the charts in section three need new labels, and the executive summary is a bit long, i'll cut it down tomorrow morning, let me know if you want me to include the appendix or leave it out, thanks felix||3/three|Clara;first pass;report;numbers;charts;section;labels;executive summary;cut it down;tomorrow morning;if;appendix;Felix||0|
eic|hi pooja ma'am the team outing is fixed for the twenty second, sorry the twenty fourth, at the resort near karjat, the bus will leave from the office at seven am sharp, kindly share your food preference by monday, thanks and regards sneha||24th/twenty-fourth;7/seven|Pooja;team outing;resort;Karjat;bus;office;sharp;food preference;Monday;Sneha||0|correction: 24th, not 22nd
p|hi everyone exclamation mark new line the trek is confirmed for sunday full stop meeting point is the old fort gate at six thirty full stop carry two litres of water each full stop|6:30|2/two|trek;confirmed;Sunday;meeting point;old fort gate;water each|exclamation mark;new line;full stop|0|
p|note to self colon the passport renewal form needs a new photo comma a copy of the old passport comma and the address proof full stop|||note to self;passport renewal form;new photo;old passport;address proof|colon;comma;full stop|0|
h|so i'm not sure if the tour company will refund us, their policy says full refund if you cancel seven days before, we're cancelling on day six, so we might only get half back, i'll call them anyway||7/seven;6/six|not sure;if;tour company;refund;policy;full refund;cancel;might;half back;anyway||1|condition + hedge kept
g|we're not doing gifts this year for the secret santa, instead everyone brings a dish, and nobody should spend money on decorations, we have plenty from last year|||gifts;this year;secret santa;instead;dish;decorations;plenty;last year||2|
n|the flight from mumbai to singapore is five hours twenty minutes, departing at eleven fifty five pm, and the return is on the ninth at two fifteen pm, the fare was thirty one thousand four hundred per person|11:55;2:15;31,400/31400|5 hours 20/five hours twenty;9th/ninth|Mumbai;Singapore;departing;return;fare;per person||0|

# ---- part 9: long rows + lists top-up ----
l|okay so here's what i need from the hardware store this weekend, um, a box of two inch screws, wall anchors for the drywall, a tub of white filler, sandpaper in the fine grade, a small paint roller with a tray, masking tape, and uh one of those stud finders because i keep drilling into nothing, oh and a pair of work gloves, the old ones are torn||2/two|hardware store;this weekend;screws;wall anchors;drywall;white filler;sandpaper;fine grade;paint roller;tray;masking tape;stud finder;work gloves;torn||1|
ln|so the race day plan is, wake up at four thirty, eat the banana and the toast by five, reach the start area by six fifteen, warm up for ten minutes, start in the second wave at six fifty, take a gel at kilometre ten and again at kilometre twenty five, and meet the family near the finish arch, the target is under three hours forty|4:30;6:15;6:50;25|5/five;10/ten;3 hours 40/3:40/three hours forty|race day;banana;toast;start area;warm up;second wave;gel;kilometre/kilometer;family;finish arch;target;under||0|
lc|the roles for the play are, um, kabir is the narrator, tanvi plays the mother, zoya plays the daughter, sorry the other way round, zoya is the mother and tanvi is the daughter, and omar does lights and sound, rehearsals are tuesdays and fridays at six||6/six|roles;play;Kabir;narrator;Zoya;mother;Tanvi;daughter;Omar;lights and sound;rehearsals;Tuesdays;Fridays||0|correction: Zoya is the mother, Tanvi the daughter
lg|so the rules for the shared kitchen at the coworking space are, label your food with your name and date, nothing stays in the fridge past friday, no fish in the microwave, wash your own mugs, and don't take the oat milk, it's not communal, the cleaners empty everything on friday evening|||shared kitchen;label;name and date;fridge;Friday;fish;microwave;own mugs;oat milk;communal;cleaners;Friday evening||4|
li|okay so the list of things to carry for the hostel, uh, the bedsheet and pillow cover, a bucket and mug, the extension board, maggi and some snacks from home, the mosquito repellent, and the documents for admission, the originals plus two sets of photocopies, and papa said keep some cash also for the first week||2/two|hostel;bedsheet;pillow cover;bucket and mug;extension board;Maggi;snacks;mosquito repellent;documents;admission;originals;photocopies;papa;cash;first week||0|
lh|ideas for the newsletter this month, um, maybe a short interview with the new team lead, a roundup of the customer wins, probably a section on the upcoming holidays, and possibly a recipe or something light, if we have space we could also add the volunteer photos from the beach clean up|||newsletter;this month;maybe;interview;new team lead;roundup;customer wins;probably;upcoming holidays;possibly;recipe;if;could;volunteer photos;beach clean-up/beach clean up/beach cleanup||0|hedges per item + condition kept
lt|so the steps to reproduce the bug are, open the app in incognito, log in with the test account qa at example dot com, add three items to the cart, apply the coupon save ten, then remove one item, and you'll see the discount doesn't recalculate, it still shows the old total, it happens on chrome and firefox but not on safari||3/three;10/ten|reproduce;incognito;test account;example;cart;coupon;remove one item;discount;recalculate;still;old total;Chrome;Firefox;Safari||2|
ln|the plan for the reading challenge is twenty four books this year, so two a month, i've done nine so far, the next three are the mystery set in venice, the biography of a chess player, and the essay collection that kabir lent me, i'm behind by about five books|24|2/two;9/nine;3/three;5/five|reading challenge;this year;a month;so far;mystery;Venice;biography;chess player;essay collection;Kabir;behind;about||0|
l|so for my morning routine i want to try, uh, no phone for the first thirty minutes, a glass of warm water, ten minutes of stretching, then journaling, then a proper breakfast, not just coffee|30|10/ten|morning routine;no phone;warm water;stretching;journaling;proper breakfast;coffee||2|
lc|the stops on the road trip are, day one pune to goa, day two rest in goa, day three goa to gokarna, wait no we skip gokarna this time, so day three is goa to hampi, and day four hampi back to pune|||road trip;Pune;Goa;rest;Hampi;back|Gokarna|0|correction: day 3 goes to Hampi; Gokarna skipped (may appear only as skipped)
lp|items colon one comma the projector cable full stop two comma the clicker full stop three comma printed handouts for twenty full stop four comma name tags full stop|20||projector cable;clicker;printed handouts;name tags|comma;full stop;colon|0|
ln|the monthly subscriptions i'm paying for are music at a hundred and nineteen, the video app at six forty nine, cloud storage at a hundred and thirty, and the gym at fifteen hundred, so about twenty four hundred total, i want to cancel the cloud one|119;649;130|1,500/1500;2,400/2400|monthly subscriptions;music;video app;cloud storage;gym;about;total;cancel||0|
e|hi omar um so i spoke to the building manager about the noise from the upstairs flat, they said they'll send a written notice this week and if it continues after that they'll involve the association, i've also started keeping a log of the dates and times, could you add any nights you noticed it too, it'll help if we need to escalate, thanks zoya|||Omar;building manager;noise;upstairs flat;written notice;this week;if it continues;association;log;dates and times;escalate;Zoya||0|condition kept
ec|hi lena the invoice for october is attached, the total is four thousand three hundred and twenty euros, sorry four thousand two hundred and thirty, i mixed up the digits, payment is due within thirty days and the bank details are the same as last time, let me know if you need a purchase order number on it, thanks marco|30|4,230/4230|Lena;invoice;October;attached;total;euros;due within;bank details;same as last time;purchase order number;Marco|4,320;4320|0|correction: 4,230, not 4,320
g|um so the car failed the inspection, the brakes aren't up to standard and the left headlight doesn't work, the garage says they can't fix the brakes until thursday because the part isn't in stock, so i won't have the car for the trip on wednesday, i'm not happy about it but there's no way around it|||car;failed;inspection;brakes;standard;left headlight;garage;until;Thursday;in stock;trip;Wednesday;happy;no way around||7|
h|so i spoke to the agent and the visa should come through in about ten working days, though it could take longer if they ask for extra documents, i'm thinking of booking a refundable ticket for now and confirming once the visa is stamped, worst case we lose a small cancellation fee||10/ten|agent;visa;should;about;working days;could;if;extra documents;thinking;refundable ticket;once;stamped;worst case;cancellation fee||0|condition + hedges kept
i|good evening ma'am, this is regarding my son's tuition fees, i have paid the first instalment of fifteen thousand online today itself, the transaction id is t x n four four eight two one, kindly update the records and share the receipt, the second instalment i'll pay by the tenth of next month as discussed, thank you|15,000/15000|44821;10th/tenth|good evening;ma'am;tuition fees;first instalment/first installment;online;today itself;transaction ID;kindly;records;receipt;second instalment/second installment;next month;as discussed||0|
c|so for the camping booking, the site is lakeview number twelve, no hang on it's number fourteen, the one closer to the water, check in is from two pm and check out by eleven, we paid three thousand two hundred for two nights, and fires are allowed only in the pits, not anywhere else|14;3,200/3200|2/two;11/eleven|camping booking;Lakeview;closer to the water;check-in/check in;check-out/check out;two nights/2 nights;fires;only;pits;anywhere else|12|1|correction: site 14, not 12
n|okay so the garage sale no sorry the plant sale numbers, we sold eighty six plants, the succulents went fastest at a hundred each, the ferns at two fifty, and the big monsteras at twelve hundred, total takings were twenty one thousand eight hundred, and we have about thirty plants left for next weekend|86;250;21,800/21800|100;1,200/1200;30|plant sale;succulents;fastest;ferns;monsteras;total takings;about;left;next weekend|garage sale|0|correction: plant sale, not garage sale
q|um so i'm thinking about switching to the annual plan but i wanted to check a few things first, is the discount still twenty percent if i upgrade mid cycle, do i lose the unused days on my current monthly plan, and can i switch back to monthly later if it doesn't work out|20||annual plan;discount;still;upgrade;mid-cycle/mid cycle;unused days;monthly plan;switch back;later;work out||1|questions stay questions; not answered
p|okay title colon weekend recap new line saturday comma we finally fixed the gate full stop sunday comma lunch with the neighbours and a long walk by the canal full stop|||weekend recap;Saturday;fixed the gate;Sunday;lunch;neighbours;long walk;canal|colon;comma;full stop;new line|0|
a|for the conference we can either send two people for all three days, or four people for just the main day, the budget covers either option, so let me know by wednesday which one the team prefers||2/two;4/four|conference;all three days/all 3 days;main day;budget;either option;Wednesday;team prefers||0|alternative: both options kept
ic|so the plan for mama's anniversary dinner, we booked the banquet at the club for saturday, no wait it's sunday the sixteenth, from seven thirty onwards, for about forty people, mummy wants only veg food and no alcohol because some elders are coming, and please don't tell mama anything, it's a surprise yaar, i'll collect the cake on the way|7:30|16th/sixteenth;40|mama;anniversary dinner;banquet;club;Sunday;onwards;about;mummy;only veg;alcohol;elders;surprise;yaar;cake|Saturday|2|correction: Sunday the 16th, not Saturday
'''

if __name__ == "__main__":
    main()
