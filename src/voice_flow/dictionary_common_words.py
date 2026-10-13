"""Frequent English words that never belong in the user dictionary.

Generated once from the wordfreq top-2000 English list (MIT / CC-BY-SA data,
https://github.com/rspeer/wordfreq) plus everyday dictation words, with
common proper nouns removed (John, London, Google, Windows...). It is static
so the app has no runtime dependency on wordfreq.
"""

COMMON_WORDS = frozenset("""
a ability able about above absolutely accept access accident according
account accounts across act acting action actions active activities activity
actual actually ad add added addition additional address administration
adult advanced advantage advice after afternoon again against age agency
agent ago agree agreed agreement ah ahead aid air airport album alive all
allow allowed almost alone along already also alternative although always am
amazing among amount an analysis and animal animals announced annual another
answer anti any anymore anyone anything anyway anywhere apart app apparently
appear appeared appears application apply appreciate approach apps are area
areas arm arms army around arrived art article articles artist as ask asked
asking ass assistant associated association at attack attempt attention
audience author authority available average avoid award awards aware away
awesome baby back background bad bag balance ball band bank bar base based
basic basis battle bay be beach bear beat beautiful beauty became because
become becomes becoming bed been before began begin beginning behind being
believe believed below benefit benefits best bet better between beyond big
bigger biggest bill billion birth birthday bit bitch black block blog blood
blue board boat body book books born boss both bottom bought box boy boys
brain brand break breaking bridge bring bringing broke broken brother
brought brown budget build building built bus business busy but buy buying
by bye call called calling calls came camera camp campaign can cancer cannot
capacity capital captain car card cards care career carried carry cars case
cases cash cast cat catch caught cause caused cell cells cent center central
centre century certain certainly chairman challenge chance change changed
changes changing channel character characters charge cheap check chief child
children choice choose christian church cities citizens city civil claim
claims class classes classic clean clear clearly click climate close closed
closer clothes club coach coast code coffee cold collection college color
come comes coming command commands comment comments commercial commission
committee common communities community companies company compared
competition complete completed completely complex computer concept concerned
condition conditions conference congress connection consider considered
construction contact content continue continued continues contract control
conversation cool copy core corner correct cost costs could council count
countries country county couple course court cover covered crazy create
created credit crime criminal critical cross cultural culture cup current
currently customers cut dad daily damage damn dance dangerous dark data date
daughter day days dead deal dear death decide decided decision decisions
deep defense definitely degree demand democratic department described
description design designed despite details develop developed development
dictionary did die died difference different difficult digital dinner direct
direction directly director discovered discussion disease distance district
division do doctor does dog dogs doing dollars done door double doubt down
draw dream dress drink drinking drive driver driving drop dropped drug drugs
dry dude due during duty each earlier early earth easier easily east eastern
easy eat eating economic economy edge edition education effect effective
effects effort efforts eight either election electric else email emails
emergency employees end ended ends energy engine engineering enjoy enough
enter entered entire entirely environment episode equipment er especially
established estate even evening event events eventually ever every everybody
everyone everything evidence evil ex exactly example excellent except
exchange excited executive exist existing expect expected experience explain
extra extremely eye eyes face fact facts failed failure fair faith fall
families family famous fan fans fantastic far farm fashion fast fat father
favorite fear feature features federal feel feeling feelings feels feet fell
fellow felt female festival few field fifth fight fighting figure figures
file film final finally financial find finding fine finish finished fire
firm first fish fit five fix flat flight floor flow fly flying focus follow
followed following follows food foot football for force forced forces
foreign forever forget form former forms forward found foundation four
fourth free freedom fresh friend friends from front fuck fucking fuel full
fully fun function fund funds funny further future gain game games garden
gas gave gay general generally generation get gets getting gift girl girls
give given gives giving glad glass global go goal goals god goes going gold
gone gonna good got gotta government governor grade grand great greater
greatest green ground group groups grow growing growth guard guess guide gun
guy guys ha had hair half hall hand handle hands happen happened happening
happens happy hard has hate have having he head health healthy hear heard
hearing heart heat heavy held hell hello help helped helping helps her here
hers herself hey hi high higher highest highly hill him himself his history
hit hmm hold holding holy home honest hope horse hospital host hot hotel
hour hours house houses housing how however huge human hundred hurt husband
i ice idea ideas if ill image images imagine immediately impact important
impossible improve in include included includes including income increase
increased indeed independent individual individuals industry influence
information initial injury inside instead institute insurance interest
interested interesting international internet interview into introduced
investigation investment involved iron is island issue issued issues it
items its itself job jobs join joined journal judge just justice keep
keeping kept key kick kid kids kill killed killing kind king knew know
knowing knowledge known knows labor lack lady lake land language large
larger largest last late later latest law laws lead leader leaders
leadership leading league learn learned learning least leave leaves leaving
led left legal length less let letter level levels library lie lies life
light like liked likely likes limited line lines link links list listen
lists literally little live lived lives living local located location long
longer look looked looking looks lord lose losing loss lost lot lots love
loved lovely low lower luck lucky machine mad made magazine magic mail main
major majority make makes making male man managed management manager many
map mark market marketing marriage married mass massive master match
material materials matter matters may maybe me mean meaning means meant
media medical medicine meet meeting meetings member members memory men
mental mention mentioned message messages met metal method mid middle might
miles military million mind mine minister minute minutes miss missed missing
mission mobile model models modern mom moment money month months more
morning most mostly mother mountain mouth move moved movement movie movies
moving much multiple murder music must my myself name named names nation
national nations natural nature near nearly necessary need needed needs
negative neither net network never new news next nice night nine no nobody
non none nope nor normal north northern not note notes nothing notice now
nuclear number numbers obviously of off offer offered offers office officer
officers official often oh oil ok okay old older on once one ones online
only onto open opened opening operating operation operations opinion
opportunity option or order ordered orders organization original other
others otherwise our ours ourselves out outside over overall own owned owner
page paid pain pair paper parents park parliament part particular
particularly parties partner parts party pass passed past patient patients
pay paying peace people per percent perfect performance perhaps period
person personal phone photo photos physical pick picked picture pictures
piece pieces place placed places plan plane planning plans plant play played
player players playing plays please plenty plus point points police policy
polish polishing political politics poor pop popular population port
position positive possible possibly post posted potential power powerful
practice pre prepared presence present presented president press pressure
pretty prevent previous previously price prices primary prime prince prior
prison private pro probably problem problems process produce produced
product production products professional professor profile program programs
progress project projects proper property protect protection proud prove
provide provided provides providing public published pull purpose push put
putting quality quarter queen question questions quick quickly quite race
radio raise raised ran range rare rate rates rather re reach reached
reaction read reading ready real reality realize really reason reasons
receive received recent recently record records red reduce reference region
regional regular related relationship release released religion religious
remain remains remember removed report reported reports request require
required research resources respect response responsibility responsible rest
result results return returned review rich ride right rights ring rise risk
river road rock role roll room rose round royal rule rules run running runs
sad safe safety said sale sales same save saw say saying says scale scene
school schools science score screen sea search season seat second seconds
secret secretary section security see seeing seem seemed seems seen self
sell selling senate send senior sense sent separate series serious seriously
serve served service services session set setting seven several sex sexual
shall shape share she ship shit shoot shooting shop short shot should show
showed showing shown shows shut sick side sides sign signed significant
silver similar simple simply since single sir sister sit site sites sitting
situation six size skills skin sky sleep slightly slow small smaller smart
so social society software sold solid solution some somebody someone
something sometimes somewhere son song songs soon sorry sort soul sound
sounds source sources south southern space speak speaking special species
specific speech speed spend spent spirit spoke sport sports spot spread
spring square staff stage stand standard standards standing star stars start
started starting starts state stated statement states station status stay
step steps stick still stock stone stop stopped store stories story straight
strategy street strength stress strong structure student students studies
study stuff stupid style subject success successful such suggest summer sun
super supply support supposed sure surface surprise sweet system systems
table take taken takes taking talk talking target task tasks taste tax tea
teacher teachers teaching team teams technical technology television tell
telling tells ten term terms test text texts than thank thanks that the
their theirs them themselves then theory there therefore these they thing
things think thinking thinks third this those though thought thoughts
thousands three through throughout throw thus till time times title to today
together told tomorrow tonight too took top total totally touch tough tour
toward towards town track trade traditional traffic train training transfer
travel treat treatment tree trial tried trip trouble true truly trust truth
try trying turn turned turns twice two type types uh um umm under understand
understanding union unique unit united units university unless until up upon
upper us use used useful users uses using usually valley value van variety
various vehicle version very via victory video videos view views village
violence visit voice volume vote wait waiting wake walk walking wall wanna
want wanted wants war was waste watch watched watching water way ways we
weapons wear wearing weather web website wedding week weekend weeks weight
weird welcome well went were west western what whatever when where whether
which while white who whole whom whose why wide wife wild will willing win
wind window wine winner winning winter wish with within without woman women
won wonder wonderful wood word words work worked workers working works world
worry worse worst worth would wow write writing written wrong wrote yeah
year years yep yes yesterday yet you young your yours yourself yourselves
youth zone
""".split())
