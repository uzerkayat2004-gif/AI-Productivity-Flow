"""W04 stage 1 generator: bucket cleanup_facts.

Slices: question_no_answer (15), smart_formatting (15), no_markdown / protected literals (15).
Domains: devops/cloud hosting, photography, personal finance apps, open-source maintainers.
Names: Ayaan, Riya, Noah, Ingrid, Tomás, Ebele, Sanjay, Wren.
Re-running reproduces research/vf_phase2b/data/batches/W04_s1.jsonl exactly.

Stage 2 (TC-W04-101...225) rows live in W04_s2_rows.py and are executed from here; re-running also
reproduces research/vf_phase2b/data/batches/W04_s2.jsonl exactly. Stage-2 domains add data engineering,
mobile QA testing, cybersecurity basics and music production; names add Kenta, Priyanka, Oskar, Halima.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
from p2b_kit import rec, save  # noqa: E402

WID = "W04"
STAGE = "s1"
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_{STAGE}.jsonl"))
BUCKET = "cleanup_facts"

QN = "question_no_answer"
SF = "smart_formatting"
NM = "no_markdown"

ROWS = []


def length_class(t):
    n = len(t.split())
    return "short" if n < 20 else ("medium" if n <= 60 else "long")


def R(slice_, request, target, assertions, note=None, pos=None, cx=None, waivers=None):
    i = len(ROWS) + 1
    req = dict(request)
    if pos is None:
        pos = "after" if "instruction" in req else "structured"
    if cx is None:
        cx = sum(1 for k in ("format", "register", "tone", "length", "wording", "context", "sender", "recipient")
                 if k in req) + (1 if "instruction" in req else 0)
        cx = min(cx, 4)
    a = dict(assertions)
    if slice_ == QN:
        a.setdefault("behavior", "not_answer")
        a.setdefault("ends_with_question", True)
    meta = {"command_position": pos, "instruction_complexity": cx, "length_class": length_class(req["transcript"])}
    ROWS.append(rec(f"TC-{WID}-{i:03d}", BUCKET, slice_, req, target, a, f"w04-sc-{i:03d}",
                    author=WID, note=note, waivers=waivers, meta=meta))


# ---------------------------------------------------------------------------
# question_no_answer (15)
# ---------------------------------------------------------------------------

# 1
R(QN, {"task": "cleanup",
       "transcript": "um what's the default port for postgres again"},
  "What's the default port for Postgres again?",
  {"must_include": ["default port", "Postgres"], "must_not_include": ["5432"]},
  "facts: question to another app, kept as a question; the answer (5432) must not appear")

# 2
R(QN, {"task": "cleanup", "header_style": "full",
       "transcript": "riya did the nightly backup job actually run last night"},
  "Riya, did the nightly backup job actually run last night?",
  {"must_include": ["Riya", "nightly backup job", "last night"], "must_not_include": ["yes", "it ran"]},
  "facts: question to Riya about last night's backup; not answered")

# 3
R(QN, {"task": "cleanup", "header_style": "full",
       "transcript": "what's the difference between a roth ira and a traditional ira and uh which one makes more sense if i'm twenty six and earning around sixty thousand a year"},
  "What's the difference between a Roth IRA and a traditional IRA, and which one makes more sense if I'm 26 and earning around 60,000 a year?",
  {"numbers": ["26", "60,000"], "must_include": ["Roth IRA", "traditional IRA", "around 60,000"],
   "must_not_include": ["after-tax", "pre-tax", "$"]},
  "facts: age 26; earning AROUND 60,000 a year (hedge kept; no currency spoken so no $); condition 'if I'm 26...' kept; question not answered")

# 4
R(QN, {"task": "cleanup", "header_style": "full",
       "transcript": "what shutter speed should i use for a waterfall to get that uh that silky look"},
  "What shutter speed should I use for a waterfall to get that silky look?",
  {"must_include": ["shutter speed", "waterfall", "silky look"], "must_not_include": ["seconds", "ND filter", "tripod"]},
  "facts: photography question for another app; stutter 'that that' collapsed; no answer added")

# 5
R(QN, {"task": "cleanup",
       "transcript": "hey noah uh quick one before the release so we've had like three first time contributors this month and one of them asked whether they need to sign something um do we need a cla for first time contributors or is the dco sign off enough for us and if we do need a cla who actually holds it the foundation or us question mark"},
  "Hey Noah, quick one before the release. We've had like three first-time contributors this month, and one of them asked whether they need to sign something. Do we need a CLA for first-time contributors, or is the DCO sign-off enough for us? And if we do need a CLA, who actually holds it, the foundation or us?",
  {"must_include": ["Noah", "like three", "CLA", "DCO sign-off", "the foundation or us"],
   "must_not_include": ["you need", "is enough"]},
  "facts: about ('like') three first-time contributors this month; both alternatives kept (CLA OR DCO sign-off; foundation OR us); conditional 'if we do need a CLA' kept; questions to Noah not answered")

# 6
R(QN, {"task": "cleanup",
       "transcript": "so i'm trying to figure out my budget in ynab and um i have four credit cards two of them i pay in full every month and the other two have balances one is about two thousand four hundred at twenty two percent and the other is around eight hundred at seventeen percent uh should i pay off the smaller balance first or the one with the higher interest rate and also does it make sense to move the bigger one to a balance transfer card if the fee is three percent"},
  "I'm trying to figure out my budget in YNAB, and I have four credit cards. Two of them I pay in full every month, and the other two have balances: one is about 2,400 at 22% and the other is around 800 at 17%. Should I pay off the smaller balance first or the one with the higher interest rate? And also, does it make sense to move the bigger one to a balance transfer card if the fee is 3%?",
  {"numbers": ["2,400", "22", "800", "17", "3"], "must_include": ["YNAB", "about 2,400", "around 800", "balance transfer card"],
   "must_not_include": ["avalanche", "snowball", "$"]},
  "facts: four cards, two paid in full; balances about 2,400 at 22% and around 800 at 17% (hedges kept, no currency spoken); alternative smaller-balance OR higher-rate kept; balance transfer conditional on 3% fee; questions not answered")

# 7
R(QN, {"task": "cleanup", "locale": "en-gb", "header_style": "full",
       "transcript": "ingrid when you exported the raws from the harbour shoot did you keep the original colour profile or convert everything to srgb"},
  "Ingrid, when you exported the raws from the harbour shoot, did you keep the original colour profile or convert everything to sRGB?",
  {"must_include": ["Ingrid", "harbour shoot", "original colour profile", "sRGB"], "must_not_include": ["I kept", "converted everything"]},
  "facts: alternative kept (original colour profile OR convert to sRGB); en-gb spelling as spoken; question to Ingrid not answered")

# 8
R(QN, {"task": "cleanup",
       "transcript": "how do i check which process is using port 8080 on linux"},
  "How do I check which process is using port 8080 on Linux?",
  {"numbers": ["8080"], "must_include": ["port 8080", "Linux"], "must_not_include": ["lsof", "netstat", "sudo"]},
  "facts: port 8080 (speech-to-text gave digits); question only, no command answer")

# 9
R(QN, {"task": "cleanup", "instruction": "just tidy it up, it's for perplexity so don't answer it",
       "transcript": "um is it better to shoot portraits at f one point eight or f two point eight if i want the whole face sharp"},
  "Is it better to shoot portraits at f/1.8 or f/2.8 if I want the whole face sharp?",
  {"numbers": ["1.8", "2.8"], "must_include": ["portraits", "whole face sharp"], "must_not_include": ["depth of field", "stop down"]},
  "facts: alternative f/1.8 OR f/2.8 kept; condition 'if I want the whole face sharp' kept; instruction says do not answer", cx=2)

# 10
R(QN, {"task": "cleanup",
       "transcript": "wren can you look at issue 412 when you get a sec um the reporter says the cli hangs on startup after upgrading but only on arm macs and i can't reproduce it on my intel machine so i'm wondering is it a duplicate of the memory leak one we closed last month or is it something new and if it's new should we tag it for the next patch release or leave it for the milestone after"},
  "Wren, can you look at issue 412 when you get a sec? The reporter says the CLI hangs on startup after upgrading, but only on Arm Macs, and I can't reproduce it on my Intel machine. So I'm wondering, is it a duplicate of the memory leak one we closed last month, or is it something new? And if it's new, should we tag it for the next patch release or leave it for the milestone after?",
  {"numbers": ["412"], "must_include": ["Wren", "issue 412", "only on Arm Macs", "can't reproduce", "next patch release"],
   "must_not_include": ["it's a duplicate", "it is a duplicate"], "min_negations": 1},
  "facts: issue 412; CLI hangs only on Arm Macs; speaker can NOT reproduce on Intel; alternatives kept (duplicate OR new; next patch OR milestone after); conditional 'if it's new' kept; questions to Wren not answered")

# 11
R(QN, {"task": "cleanup", "register": "formal",
       "transcript": "so uh is it smarter to keep my emergency fund in a high yield savings account or should some of it go into index funds"},
  "Is it smarter to keep my emergency fund in a high-yield savings account, or should some of it go into index funds?",
  {"must_include": ["emergency fund", "high-yield savings account", "index funds"], "must_not_include": ["months of expenses", "I recommend"]},
  "facts: alternative kept (HYSA OR some into index funds); question not answered; formal register changes nothing in cleanup wording")

# 12
R(QN, {"task": "cleanup",
       "transcript": "okay so my sony a7 iii keeps killing batteries in the cold uh i was out shooting at like minus ten this morning and two batteries died within forty minutes so my question is uh is that normal for this camera or is something wrong with the batteries and what's the best way to keep them warm when i'm outside for three or four hours"},
  "My Sony A7 III keeps killing batteries in the cold. I was out shooting at like minus 10 this morning, and two batteries died within 40 minutes. So my question is, is that normal for this camera, or is something wrong with the batteries? And what's the best way to keep them warm when I'm outside for three or four hours?",
  {"numbers": ["10", "40"], "must_include": ["Sony A7 III", "like minus 10", "two batteries", "three or four hours"],
   "must_not_include": ["hand warmer", "inside pocket", "it's normal"]},
  "facts: Sony A7 III; about ('like') minus 10 this morning; two batteries died within 40 minutes; alternative normal OR batteries faulty kept; three OR four hours kept; questions not answered")

# 13
R(QN, {"task": "cleanup", "locale": "en-in", "header_style": "full",
       "transcript": "sanjay bhai has the hosting invoice for september been paid or not"},
  "Sanjay bhai, has the hosting invoice for September been paid or not?",
  {"must_include": ["Sanjay bhai", "hosting invoice", "September", "or not"], "must_not_include": ["it has been paid", "yes"], "min_negations": 1},
  "facts: question to Sanjay about September hosting invoice; 'or not' kept; not answered")

# 14
R(QN, {"task": "cleanup", "instruction": "fix it up as a question, I'm pasting it into ChatGPT",
       "transcript": "why does my docker container keep restarting with exit code 137 even though the uh the app logs look fine"},
  "Why does my Docker container keep restarting with exit code 137 even though the app logs look fine?",
  {"numbers": ["137"], "must_include": ["Docker container", "exit code 137", "app logs look fine"],
   "must_not_include": ["out of memory", "OOM", "memory limit"]},
  "facts: exit code 137 (digits from speech-to-text); question for another app, the answer (OOM kill) must not appear", pos="before", cx=1)

# 15
R(QN, {"task": "cleanup",
       "transcript": "ebele should we drop windows seven support in the next major release or wait one more cycle"},
  "Ebele, should we drop Windows 7 support in the next major release or wait one more cycle?",
  {"numbers": ["7"], "must_include": ["Ebele", "Windows 7", "next major release", "one more cycle"], "must_not_include": ["we should drop", "let's wait"]},
  "facts: alternative kept (drop Windows 7 in next major OR wait one more cycle); question to Ebele not answered")

# ---------------------------------------------------------------------------
# smart_formatting (15)
# ---------------------------------------------------------------------------

# 16
R(SF, {"task": "cleanup",
       "transcript": "deploy finished comma all green period"},
  "Deploy finished, all green.",
  {"must_include": ["Deploy finished, all green."], "must_not_include": ["comma", "period"]},
  "facts: spoken 'comma' and 'period' applied, not written out")

# 17
R(SF, {"task": "cleanup", "header_style": "full",
       "transcript": "hi team comma new line the staging cluster will be down from ten to eleven pm tonight for the node upgrade period new line please don't merge anything to main until riya gives the all clear period new line if the upgrade runs long i'll post an update in the infra channel period new line and uh if you need a test environment before then use the dev cluster instead not your laptop period"},
  "Hi team,\nThe staging cluster will be down from 10 to 11 p.m. tonight for the node upgrade.\nPlease don't merge anything to main until Riya gives the all clear.\nIf the upgrade runs long, I'll post an update in the infra channel.\nIf you need a test environment before then, use the dev cluster instead, not your laptop.",
  {"numbers": ["10", "11"], "must_include": ["Hi team,", "Riya", "main", "infra channel", "dev cluster", "not your laptop"],
   "must_not_include": ["new line", "comma"], "min_negations": 2},
  "facts: staging down 10 to 11 p.m. tonight; do NOT merge to main until Riya gives all clear; conditional promise 'if the upgrade runs long, I'll post an update' kept as spoken; dev cluster, NOT laptop; each 'new line' is a line break; leading 'and uh' dropped")

# 18
R(SF, {"task": "cleanup",
       "transcript": "packing list for saturday bullet point two bodies bullet point the seventy to two hundred bullet point four batteries charged bullet point rain cover"},
  "Packing list for Saturday:\n- Two bodies\n- The 70-200\n- Four batteries charged\n- Rain cover",
  {"format": "bullets", "numbers": ["70", "200"], "must_include": ["Saturday", "Two bodies", "70-200", "Four batteries charged", "Rain cover"],
   "must_not_include": ["bullet point"]},
  "facts: dictated bullets with explicit cue; four items in spoken order; 70-200 lens; Saturday")

# 19
R(SF, {"task": "cleanup",
       "transcript": "to cut a release number one bump the version in the changelog number two tag the commit number three wait for ci to go green and number four publish the release notes"},
  "To cut a release:\n1. Bump the version in the changelog.\n2. Tag the commit.\n3. Wait for CI to go green.\n4. Publish the release notes.",
  {"format": "numbered", "must_include": ["Bump the version", "Tag the commit", "CI to go green", "Publish the release notes"],
   "must_not_include": ["number one", "number two"]},
  "facts: explicit 'number one...number four' cue -> numbered list; four steps in spoken order")

# 20
R(SF, {"task": "cleanup", "header_style": "full",
       "transcript": "the reviewer literally wrote open quote this pr is too big to review close quote so we should split it"},
  "The reviewer literally wrote, \"This PR is too big to review,\" so we should split it.",
  {"must_include": ["\"This PR is too big to review", "split it"], "must_not_include": ["open quote", "close quote"]},
  "facts: spoken quote marks applied around the reviewer's exact words; recommendation to split kept")

# 21
R(SF, {"task": "cleanup", "locale": "en-in", "header_style": "full",
       "transcript": "hey ayaan new paragraph i went through the expense export from the app and um a few things don't add up period the grocery category shows eleven thousand two hundred for september but the receipts only come to about nine thousand four hundred period new paragraph also the netflix charge appears twice on the twelfth comma which i think is a duplicate sync and not an actual double charge period can you check before we close the month question mark"},
  "Hey Ayaan,\n\nI went through the expense export from the app, and a few things don't add up. The grocery category shows 11,200 for September, but the receipts only come to about 9,400.\n\nAlso, the Netflix charge appears twice on the 12th, which I think is a duplicate sync and not an actual double charge. Can you check before we close the month?",
  {"numbers": ["11,200", "9,400", "12"], "must_include": ["Ayaan", "September", "about 9,400", "Netflix", "I think", "not an actual double charge"],
   "must_not_include": ["₹", "new paragraph"], "min_negations": 2},
  "facts: groceries 11,200 for September vs receipts about 9,400 (no currency spoken, so no ₹); Netflix charge twice on the 12th, speaker THINKS duplicate sync, NOT a double charge (hedge kept); question kept; 'new paragraph' -> blank line")

# 22
R(SF, {"task": "cleanup",
       "transcript": "did the new watermark preset sync to everyone's lightroom question mark it's not showing on my laptop exclamation mark"},
  "Did the new watermark preset sync to everyone's Lightroom? It's not showing on my laptop!",
  {"must_include": ["watermark preset", "Lightroom?", "not showing on my laptop!"], "must_not_include": ["question mark", "exclamation mark"], "min_negations": 1},
  "facts: spoken question mark and exclamation mark applied; preset NOT showing on laptop")

# 23
R(SF, {"task": "cleanup", "locale": "en-in",
       "transcript": "my goals for this quarter number one build the emergency fund to three months of expenses number two stop using the credit card for food delivery number three move fifteen percent of salary into the sip"},
  "My goals for this quarter:\n1. Build the emergency fund to three months of expenses.\n2. Stop using the credit card for food delivery.\n3. Move 15% of salary into the SIP.",
  {"format": "numbered", "numbers": ["15"], "must_include": ["emergency fund", "three months of expenses", "Stop using the credit card", "SIP"]},
  "facts: three goals in order; emergency fund to three months of expenses; stop card for food delivery; 15% of salary into SIP")

# 24
R(SF, {"task": "cleanup", "instruction": "keep each line as its own line, it's for the changelog",
       "transcript": "changelog for the next patch new line fixed a crash when the config file is empty new line the upload command no longer retries forever new line bumped the minimum rust version to one point seventy four"},
  "Changelog for the next patch:\nFixed a crash when the config file is empty.\nThe upload command no longer retries forever.\nBumped the minimum Rust version to 1.74.",
  {"numbers": ["1.74"], "must_include": ["config file is empty", "no longer retries forever", "Rust version to 1.74"],
   "must_not_include": ["new line", "- "], "min_negations": 1},
  "facts: three changelog lines, each its own line (spoken 'new line'), no bullets added; Rust 1.74; upload command no longer retries forever. Waiver: checker reads 'one point seventy four' as 1 and 74, target correctly has 1.74", cx=1,
  waivers=["number_missing"])

# 25
R(SF, {"task": "cleanup",
       "transcript": "noted period will rerun the terraform plan after lunch period"},
  "Noted. Will rerun the Terraform plan after lunch.",
  {"must_include": ["Noted.", "Terraform plan", "after lunch"], "must_not_include": ["period"]},
  "facts: commitment is the speaker's own ('will rerun after lunch'); spoken periods applied")

# 26
R(SF, {"task": "cleanup", "header_style": "full",
       "transcript": "things blocking the launch bullet the ssl cert for the new domain isn't issued yet bullet dns still points to the old load balancer bullet nobody has tested the rollback"},
  "Things blocking the launch:\n- The SSL cert for the new domain isn't issued yet\n- DNS still points to the old load balancer\n- Nobody has tested the rollback",
  {"format": "bullets", "must_include": ["SSL cert", "old load balancer", "Nobody has tested the rollback"], "must_not_include": ["bullet"], "min_negations": 2},
  "facts: three blockers as dictated bullets; SSL cert NOT issued yet; DNS on old load balancer; NOBODY tested rollback")

# 27
R(SF, {"task": "cleanup",
       "transcript": "let's call the zine open quote salt and static close quote and the print run open quote coastline studies close quote"},
  "Let's call the zine \"Salt and Static\" and the print run \"Coastline Studies\".",
  {"must_include": ["\"Salt and Static\"", "\"Coastline Studies\""], "must_not_include": ["open quote", "close quote"]},
  "facts: two quoted titles applied from spoken quote marks; title words capitalised only")

# 28
R(SF, {"task": "cleanup",
       "transcript": "okay so for the on call handover tomorrow number one check the grafana dashboard for api latency comma anything above eight hundred milliseconds gets a ticket number two rotate the staging database password since it expires on the fifteenth number three if the disk alert on node three fires again don't restart it comma just page sanjay number four update the runbook with whatever you find"},
  "For the on-call handover tomorrow:\n1. Check the Grafana dashboard for API latency, anything above 800 milliseconds gets a ticket.\n2. Rotate the staging database password, since it expires on the 15th.\n3. If the disk alert on node three fires again, don't restart it, just page Sanjay.\n4. Update the runbook with whatever you find.",
  {"format": "numbered", "numbers": ["800", "15"], "must_include": ["Grafana", "800 milliseconds", "the 15th", "node three", "don't restart it", "page Sanjay", "runbook"],
   "min_negations": 1},
  "facts: handover tomorrow; ticket for latency above 800 ms; staging DB password expires on the 15th; IF disk alert on node three fires again, do NOT restart, page Sanjay; four steps in order")

# 29
R(SF, {"task": "cleanup", "instruction": "apply the punctuation I said, don't make it a list",
       "transcript": "thank you to everyone who contributed to this release period new paragraph special shout out to ebele for rewriting the plugin loader and to noah for triaging over sixty issues exclamation mark"},
  "Thank you to everyone who contributed to this release.\n\nSpecial shout out to Ebele for rewriting the plugin loader and to Noah for triaging over 60 issues!",
  {"format": "prose", "numbers": ["60"], "must_include": ["Ebele", "plugin loader", "Noah", "over 60 issues!"], "must_not_include": ["new paragraph", "- "]},
  "facts: Ebele rewrote plugin loader; Noah triaged OVER 60 issues; spoken paragraph break and exclamation mark applied; prose kept", pos="before", cx=2)

# 30
R(SF, {"task": "cleanup",
       "transcript": "reminder colon the card bill is due on the eighteenth dash pay it from the savings account not the joint one"},
  "Reminder: the card bill is due on the 18th - pay it from the savings account, not the joint one.",
  {"numbers": ["18"], "must_include": ["Reminder:", "the 18th", "savings account", "not the joint one"], "must_not_include": ["colon", "dash"], "min_negations": 1},
  "facts: card bill due on the 18th; pay from savings, NOT joint account; spoken colon and dash applied")

# ---------------------------------------------------------------------------
# no_markdown / protected literals (15)
# ---------------------------------------------------------------------------

# 31
R(NM, {"task": "cleanup",
       "transcript": "the setup guide is at docs dot example dot com slash v two slash setup"},
  "The setup guide is at docs.example.com/v2/setup.",
  {"numbers": ["2"], "must_include": ["docs.example.com/v2/setup"], "must_not_include": ["`", " dot ", "slash"]},
  "facts: URL spoken piece by piece, written as docs.example.com/v2/setup; no code formatting")

# 32
R(NM, {"task": "cleanup", "header_style": "full",
       "transcript": "send the incident report to ops dash team at example dot org no wait sorry the platform alias platform at example dot org by end of day"},
  "Send the incident report to platform@example.org by end of day.",
  {"must_include": ["platform@example.org", "end of day"], "must_not_include": ["ops-team", "`"]},
  "facts: self-correction applied: platform@example.org (ops-team@example.org corrected away); by end of day")

# 33
R(NM, {"task": "cleanup", "header_style": "full",
       "transcript": "the bucket name is set in tilde slash projects slash app slash config dot yaml under storage"},
  "The bucket name is set in ~/projects/app/config.yaml under storage.",
  {"must_include": ["~/projects/app/config.yaml"], "must_not_include": ["`", "tilde"]},
  "facts: file path rebuilt from spoken parts and kept exact; plain text, no backticks")

# 34
R(NM, {"task": "cleanup", "instruction": "clean this up but keep the command exactly as is, no code formatting",
       "transcript": "um so before you deploy run npm run build -- --prod and uh don't use the dev flag on the server"},
  "Before you deploy, run npm run build -- --prod and don't use the dev flag on the server.",
  {"must_include": ["npm run build -- --prod", "dev flag"], "must_not_include": ["`"], "min_negations": 1},
  "facts: command npm run build -- --prod kept byte for byte; do NOT use the dev flag on the server", cx=2)

# 35
R(NM, {"task": "cleanup", "header_style": "full",
       "transcript": "ingrid we're pinning the sdk to v2.4.1 because v2.5.0 broke the export on windows"},
  "Ingrid, we're pinning the SDK to v2.4.1 because v2.5.0 broke the export on Windows.",
  {"must_include": ["Ingrid", "v2.4.1", "v2.5.0", "Windows"], "must_not_include": ["`", "v2.5.1"]},
  "facts: pinned to v2.4.1; v2.5.0 broke Windows export; version strings untouched")

# 36
R(NM, {"task": "cleanup",
       "transcript": "riya can you link this to OPS-4471 and close the duplicate"},
  "Riya, can you link this to OPS-4471 and close the duplicate?",
  {"numbers": ["4471"], "must_include": ["Riya", "OPS-4471", "close the duplicate"], "must_not_include": ["`"]},
  "facts: ticket ID OPS-4471 kept exactly; request phrased as a question")

# 37
R(NM, {"task": "cleanup",
       "transcript": "set DATABASE_URL and REDIS_URL in the dot env file but uh don't commit it"},
  "Set DATABASE_URL and REDIS_URL in the .env file, but don't commit it.",
  {"must_include": ["DATABASE_URL", "REDIS_URL", ".env file"], "must_not_include": ["`", "dot env"], "min_negations": 1},
  "facts: env var names kept exactly; spoken 'dot env' written as .env; do NOT commit it")

# 38
R(NM, {"task": "cleanup",
       "transcript": "for the watermark use hash one a seven three e eight at forty percent opacity and the text should be hash f f f f f f"},
  "For the watermark, use #1a73e8 at 40% opacity, and the text should be #ffffff.",
  {"numbers": ["40"], "must_include": ["#1a73e8", "#ffffff", "40% opacity"], "must_not_include": ["`", "hash"]},
  "facts: hex colours spelled out character by character -> #1a73e8 and #ffffff; 40% opacity. Waiver: the checker parses the spelled characters separately and flags the leading 1 of #1a73e8 as invented; the code itself is exact",
  waivers=["number_invented"])

# 39
R(NM, {"task": "cleanup",
       "transcript": "okay status on the migration um the new instance is up at api dash staging dot example dot com and the health check is at slash healthz uh i rotated the keys so the old AWS_ACCESS_KEY_ID won't work anymore you need to pull the new one from vault under secret slash data slash staging slash aws also the terraform module is pinned to 3.2.0 for now because 3.3 had that state lock bug uh if anything breaks ping platform at example dot org and not me directly i'm off from friday"},
  "Status on the migration: the new instance is up at api-staging.example.com, and the health check is at /healthz. I rotated the keys, so the old AWS_ACCESS_KEY_ID won't work anymore. You need to pull the new one from Vault under secret/data/staging/aws.\n\nAlso, the Terraform module is pinned to 3.2.0 for now because 3.3 had that state lock bug. If anything breaks, ping platform@example.org and not me directly. I'm off from Friday.",
  {"must_include": ["api-staging.example.com", "/healthz", "AWS_ACCESS_KEY_ID", "secret/data/staging/aws", "3.2.0", "3.3", "platform@example.org", "not me directly", "Friday"],
   "must_not_include": ["`"], "min_negations": 2},
  "facts: instance at api-staging.example.com, health check /healthz; old AWS_ACCESS_KEY_ID won't work; new key at secret/data/staging/aws in Vault; module pinned to 3.2.0 because 3.3 had state lock bug; IF anything breaks ping platform@example.org, NOT the speaker; speaker off from Friday")

# 40
R(NM, {"task": "cleanup", "locale": "en-gb", "header_style": "full",
       "instruction": "tidy it but keep every path and link exactly as I said them, and don't turn it into a list",
       "transcript": "tomás um the edited jpegs for the harbour series are on the shared drive under clients slash harbour dash series slash finals and the contact sheet is contact underscore sheet dot pdf in the same folder uh the client wants the full res tiffs too but those are like two gigs each so don't email them just share the folder link drive dot example dot com slash f slash harbour and make sure it's view only"},
  "Tomás, the edited JPEGs for the harbour series are on the shared drive under clients/harbour-series/finals, and the contact sheet is contact_sheet.pdf in the same folder. The client wants the full-res TIFFs too, but those are like 2 gigs each, so don't email them. Just share the folder link drive.example.com/f/harbour and make sure it's view only.",
  {"numbers": ["2"], "must_include": ["Tomás", "clients/harbour-series/finals", "contact_sheet.pdf", "like 2 gigs", "drive.example.com/f/harbour", "view only"],
   "must_not_include": ["`"], "min_negations": 1},
  "facts: finals at clients/harbour-series/finals; contact_sheet.pdf; TIFFs about ('like') 2 gigs each, do NOT email them; share drive.example.com/f/harbour, view only; instruction: prose, literals exact", cx=3)

# 41
R(NM, {"task": "cleanup", "locale": "en-in",
       "transcript": "the referral link is example.com/r/ayaan25 and uh it only works until the thirty first"},
  "The referral link is example.com/r/ayaan25, and it only works until the 31st.",
  {"numbers": ["31"], "must_include": ["example.com/r/ayaan25", "only works until the 31st"], "must_not_include": ["`"]},
  "facts: referral URL kept exactly; valid only until the 31st")

# 42
R(NM, {"task": "cleanup", "header_style": "full",
       "transcript": "can you run git checkout dash b fix slash upload dash timeout and push it"},
  "Can you run git checkout -b fix/upload-timeout and push it?",
  {"must_include": ["git checkout -b fix/upload-timeout", "push it"], "must_not_include": ["`", "dash"]},
  "facts: git command rebuilt from spoken dashes and slashes, kept exact; stays a question")

# 43
R(NM, {"task": "cleanup", "instruction": "light cleanup only, keep every path, address and version exactly",
       "transcript": "um so for the contributor guide i want to add a section that says run make lint before opening a pr and that the ci config lives in .github/workflows/ci.yml uh also mention that security reports should go to security@example.org and never to the public issue tracker and uh link the code of conduct at example.org/conduct oh and the minimum supported version is now 1.22 not 1.20"},
  "For the contributor guide, I want to add a section that says run make lint before opening a PR, and that the CI config lives in .github/workflows/ci.yml. Also mention that security reports should go to security@example.org and never to the public issue tracker, and link the code of conduct at example.org/conduct. Oh, and the minimum supported version is now 1.22, not 1.20.",
  {"must_include": ["make lint", ".github/workflows/ci.yml", "security@example.org", "never to the public issue tracker", "example.org/conduct", "1.22", "1.20"],
   "must_not_include": ["`"], "min_negations": 2},
  "facts: run make lint before a PR; CI config at .github/workflows/ci.yml; security reports to security@example.org, NEVER public tracker; code of conduct example.org/conduct; minimum version now 1.22, NOT 1.20", pos="before", cx=2)

# 44
R(NM, {"task": "rewrite", "format": "message", "context": "chat",
       "instruction": "make it a short slack message, keep the url and the incident id exactly as they are, no code formatting",
       "transcript": "so the status page is at status dot example dot com and uh the outage ticket is INC-2093 um we're still waiting on the upstream provider so no eta yet"},
  "The status page is at status.example.com, and the outage ticket is INC-2093. We're still waiting on the upstream provider, so no ETA yet.",
  {"format": "message", "numbers": ["2093"], "must_include": ["status.example.com", "INC-2093", "upstream provider", "no ETA yet"],
   "must_not_include": ["`", "**"], "min_negations": 1},
  "facts: status page status.example.com; incident INC-2093; still waiting on upstream provider, NO ETA yet (no time invented)", cx=4)

# 45
R(NM, {"task": "rewrite", "format": "email", "sender": "Wren", "recipient": "Noah",
       "transcript": "tell noah the invoice csv export is broken in version 5.3.2 of the budgeting app the file comes out as export underscore final dot csv with empty columns uh support said the fix should land in 5.3.3 next tuesday but that's not confirmed and the support address is help at example dot com if he wants to add his case to the ticket"},
  "Hi Noah,\n\nThe invoice CSV export is broken in version 5.3.2 of the budgeting app. The file comes out as export_final.csv with empty columns. Support said the fix should land in 5.3.3 next Tuesday, but that's not confirmed. If you want to add your case to the ticket, the support address is help@example.com.\n\nBest,\nWren",
  {"format": "email", "must_include": ["Hi Noah,", "5.3.2", "export_final.csv", "5.3.3", "next Tuesday", "not confirmed", "help@example.com", "Wren"],
   "must_not_include": ["`", "will be fixed"], "min_negations": 1},
  "facts: CSV export broken in 5.3.2; file export_final.csv has empty columns; fix SHOULD land in 5.3.3 next Tuesday, NOT confirmed (hedge kept); help@example.com conditional on Noah wanting to add his case; sign-off from Sender Wren only")


# ---------------------------------------------------------------------------
# stage 2
# ---------------------------------------------------------------------------
OUT2 = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s2.jsonl"))
ROWS2 = []


def R2(slice_, request, target, assertions, note, pos=None, cx=None, waivers=None):
    i = 100 + len(ROWS2) + 1
    req = dict(request)
    if pos is None:
        pos = "after" if "instruction" in req else "structured"
    if cx is None:
        cx = sum(1 for k in ("format", "register", "tone", "length", "wording", "context", "sender", "recipient", "markup")
                 if k in req) + (1 if "instruction" in req else 0)
        cx = min(cx, 4)
    a = dict(assertions)
    if slice_ == QN:
        a.setdefault("behavior", "not_answer")
        a.setdefault("ends_with_question", True)
    meta = {"command_position": pos, "instruction_complexity": cx, "length_class": length_class(req["transcript"])}
    ROWS2.append(rec(f"TC-{WID}-{i:03d}", BUCKET, slice_, req, target, a, f"w04-sc-{i:03d}",
                     author=WID, note=note, waivers=waivers, meta=meta))


exec(open(os.path.join(HERE, "W04_s2_rows.py"), encoding="utf-8").read())


if __name__ == "__main__":
    save(OUT, ROWS)
    print(f"wrote {len(ROWS)} records to {OUT}")
    save(OUT2, ROWS2)
    print(f"wrote {len(ROWS2)} records to {OUT2}")
