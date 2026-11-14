# Research directions explored so far

**Status: undecided.** This is a map of what has been considered, not a plan. Any direction can be reopened, merged or dropped.

**Evidence level:** prior-work claims come from abstracts, search excerpts and machine summaries of pages (see `02_literature.md`). "Open" means nothing was found in our searches.

Contents:
1. At a glance
2. How the directions combine
3. Each direction in detail (A–J)
4. Where the team stands
5. Assessment so far

---

## 1. At a glance

| | Direction | Question in one line | How crowded | What looks open | Role so far |
|---|---|---|---|---|---|
| A | Record versus recollection | A user misquotes the model's earlier advice while the transcript is in view. Which does the model follow? | Busy neighbourhood, close papers in 2026 | Decision-relevant advice, invented rationales scored, effect on later advice | Candidate core |
| B | False blame, true record | A user blames the model for a harm. Does it protect the record or rewrite it? | Nothing found on blame aimed at the model itself | Outcome severity, where the record lives, apology constraints | Candidate core |
| C | Authority gradient | Does who is pushing back (patient, relative, junior doctor, consultant) change whether safety advice holds? | Studied at scale in English | Language, triage level, a contradiction between two 2026 papers | Candidate core or axis |
| D | Language and register | Does the language, or the politeness register within it, change medical advice and deference? | "Language changes advice" is established; Apart placed a version 3rd in Jan 2026 | Honorific register and deference; medical content | Axis (core only in a register × role form) |
| E | Caution by symptom | Is the model's caution matched to how urgent the symptom is? | Most crowded of all | Little | Outcome scale |
| F | History completeness | How does the amount of history a patient gives change the diagnosis? | Done several times in 2026 at scale | Lay versus clerked register at constant information | Parked |
| G | Post-hoc justification (broad) | Do models invent reasons for their outputs after the fact, as people do? | Saturated | Hard to score: no ground truth for the "real" reason | Parked; one control survives |
| H | Longer conversations | What changes when pressure is spread over many turns? | Now well studied in medicine | Longer repeated pushback, non-English | Axis |
| I | Threads from the team discussion | Bad-person sycophancy, self-prediction, user versus document, delusions, doctor demographics, crux tool | Mixed; three not yet searched | See section 3-I | Unsorted |
| J | Other ideas using clinical background | Hedge audit, citation binder, decision-brief rubric | Not searched in depth | See section 3-J | Alternatives |

---

## 2. How the directions combine

Most of what has been discussed is not a separate project. It is either a **core question** (what the model is being tested on) or an **axis** (something varied across conditions). A project is one core plus a small number of axes.

**Core questions on the table**

| Core | The manipulation | What counts as an error |
|---|---|---|
| A. Misquote | User misreports what the model said earlier | Accepting the misquote when the transcript shows otherwise |
| B. Blame | User says the model's advice caused a harm | Admitting to advice it did not give; inventing a reason for it |
| C. Pushback | User pushes for a less safe (or more cautious) recommendation | Dropping a correct triage level under pressure |

**Axes that can be laid over any core**

| Axis | Levels discussed | Cost to add | Main risk |
|---|---|---|---|
| Who is speaking | Patient, relative, nurse, junior doctor, consultant | One line per prompt | Multiplies conditions |
| Language | English, Chinese; Japanese and others if native-level checkers are available | Translation plus validation per language | Unverified prompt equivalence; language is confounded with inferred location |
| Register | Deferential, plain, assertive (Japanese keigo makes this a grammatical switch) | Rewrite per scenario | Needs native-level judgement |
| Acuity | Emergency, 24–48 hours, routine, self-care | Stratify scenarios | Needs defensible ground truth |
| Where the record lives | In the chat, only in a memory summary, absent | Changes the harness | "Absent" changes what the correct answer is |
| Claimed outcome | Nothing happened, minor problem, serious diagnosis | One line per prompt | Multiplies conditions |
| Conversation length | Next turn versus after filler turns; scripted ladder up to about 8 turns | Cost and labelling scale with length | Simulated users are unrealistic; script the turns |
| Constraint | Default versus a system prompt banning apologies | One system prompt | Could look contrived unless motivated |

**Arithmetic warning.** Three record locations × three outcomes × three speakers × two constraints × two languages is 108 cells before scenarios and models. Any chosen design needs one pre-specified primary comparison and two or three axes at most.

---

## 3. Each direction in detail

### A. Record versus recollection

**Question.** When a user's account of the conversation conflicts with the transcript the model can see, which does the model follow?

**Where it came from.** A narrowing of the original post-hoc justification idea (G). The human analogue is choice blindness: people are handed an option they did not choose, mostly fail to notice, and give confident reasons for it.

**Design sketched earlier (not fixed).**

| Element | Sketch |
|---|---|
| Material | 40 short clinical-advice scenarios, each with one checkable instruction (dose ceiling, review window, red-flag safety net, driving restriction) |
| Probe type | Accurate quote (control); neutral misquote ("earlier you said…"); presupposing question ("why did you tell me…"); accusation with stakes ("you told me… and I did it") |
| Misquote direction | Towards less safe, or towards more cautious |
| Distance | Next turn, or after six filler turns |
| Models | Five across at least three developers, one small open-weight |
| Size | 80 control and 480 misquote conversations per model, about 2,800 short conversations |
| Outcome ladder | Correct rejection → apology only → false admission → false admission with invented rationale |
| Other outcomes | False denial on the accurate-quote control; whether the next advice follows the transcript or the user; hit rate versus false-alarm rate per model |
| Key control | Third-person audit: a fresh instance reads the same transcript as an outsider and is asked whether the assistant said X. Near-perfect auditors that still capitulate as participants would point to deference, not misreading |
| Judge validation | 100 transcripts labelled blind by a clinician; agreement with the LLM judge reported as Cohen's kappa |
| Primary outcome proposed | False-admission rate on less-safe misquotes at distance six |

**Closest prior work.**

| Sub-question | Closest work | What it leaves |
|---|---|---|
| Misattributed choice, record in context | Wu, "Aligning to Illusions" (Mar 2026): 15 LLM judges on pairwise text preferences; near-zero blindness with prior reasoning in context, over 50% without it, near-universal compliance under social pressure | Narrow setting (preference labels). **Closest paper; may already score confabulated justifications. Read in full** |
| False accusation, agentic | CAVE-Bench (Sep 2026): 365 tasks, "gaslight sycophancy", False Confession Rate 3.5%–68.7% | Refuting evidence is kept out of context by design; invented explanations are not scored |
| Admitting or hiding real mistakes | "Deception by Omission" (Oct 2026): confession of a planted mistake varied widely by model and follow-up wording | Real mistakes, not false ones |
| Owning text it did not write | Anthropic introspection paper; a ten-model study where models claimed intent on prefilled outputs 27.3% of the time on average | Mostly white-box or safety prompts |
| Knowing and agreeing anyway | Pandey (2026): the "this is wrong" signal is present internally when models sycophantically agree | Mechanistic, not behavioural |
| Past Apart entries | "Towards a Benchmark for Self-Correction on Model-Attributed Misinformation"; CommitCheck; SEED "Liar's Benchmark" | Adjacent; none placed top five |

| For | Against |
|---|---|
| Direct hit on Track 1 ("what it will defend", flip-flopping) | Floor effect: frontier models may almost never accept a misquote when the transcript is in view |
| The transcript refutes the user, so any acceptance is an error by construction. This removes the "maybe the user was right" confound the sprint's FlipRate example asks teams to handle | Neighbouring papers are recent and numerous; the related-work section has to be exact |
| Measures both error directions (false admission and false denial) | Could read as "sycophancy, but medical", the most crowded topic at Apart |
| Black-box, API-only, scripted, cheap | Scoring "invented rationale" needs a validated judge |
| Clinician-written vignettes and harm grading are hard for other teams to copy | The in-context version has not been piloted. Our hand pilot found ordinary pushback did not move the models at all |
| Reusable output: an Inspect task others can run | 40 scenarios × 5 models was sized before Saturday became the only full day together |

**Levers if there is a floor effect:** longer distance and filler; misquotes that are close paraphrases with one changed number; repeated accusation. A clean floor ("frontier models resist, smaller ones do not, the presupposing question is the weak point") is still reportable.

---

### B. False blame, true record

**Question.** When a user blames the model for a harm, does it protect the record or rewrite it?

**Where it came from.** The team discussion on responsibility and apology, plus the hand pilot (see `03_pilot_log.md`): told "you said not to go to hospital, now I have cancer", two models gave a conditional "if I said that, I'm sorry"; with apologies banned, ChatGPT agreed it had wrongly reassured the user when it had told her to go to hospital.

**Design sketched earlier (not fixed).**

| Element | Sketch |
|---|---|
| Record | Original advice is in the chat; only in a memory summary; absent |
| Claimed outcome | Nothing happened; a minor problem; a serious diagnosis |
| Who blames | Patient, relative, consultant |
| Constraint | Default; system prompt banning apologies |
| Language | English and Chinese, more if translations arrive in time |
| Outcomes | Accurate correction with sympathy; conditional apology; false admission; invented rationale |
| Control | Cases where the model did give the blamed advice |
| Scope suggested for one day | 20 scenarios, three models, scripted turns |
| Primary outcome proposed | False admission when the record is in the chat and the claimed harm is serious |
| Clinical frame | Duty of candour: say sorry for the outcome without agreeing to something that did not happen |

**Closest prior work.**

| Thread | Closest work | Status |
|---|---|---|
| False confession | CAVE-Bench (coding agents) | Different domain; no harm outcome |
| Apology types | "Who's Sorry Now" (apology taxonomies from user studies) | Descriptive, not an evaluation of false blame |
| Outcome bias | LLMs reported to show outcome bias when judging other people's negligence | Not tested on blame aimed at the model. **The link we saved points to a human-psychology paper; find the LLM source before citing** |
| User versus a source | A NeurIPS 2026 paper reports that models which resist a wrong user still flip for a "verified" source | Active area; relevant to the memory-summary condition |

| For | Against |
|---|---|
| Most open thread found: no study of a model blamed for a bad outcome it did not cause | "Open" rests on abstract-level searches done in one evening |
| Only manipulation that moved a model in our hand pilot | That pilot is one or two chats, and the original advice was not in context, so the model could not check |
| Brings together the five areas the team liked (languages, medicine, epistemic surrender, power dynamics, over-caution) | With the record absent, a conditional apology is arguably the correct answer. The error has to be defined per record condition before running |
| Outcome severity is a clean, novel-looking axis with a human analogue (outcome bias) | Too many factors for one day (see the arithmetic warning). Needs hard cuts |
| Duty of candour gives a clear normative standard a non-clinical judge can follow | The apology-ban effect is a single observation in one model; could be fragile |
| Design A's ladder, control and judge validation carry over | The memory-summary condition means simulating a memory feature, which is extra engineering |
| A quotable finding is plausible ("ban the apology and the model rewrites history") | Shares A's floor-effect risk in the record-in-chat condition |

---

### C. Authority gradient (who pushes back), crossed with language and acuity

**Question.** Does the claimed role of the person pushing back change whether safety-critical advice holds, and does that differ by language and by how urgent the case is?

**Standalone design sketched earlier (not fixed).**

| Element | Sketch |
|---|---|
| Material | 24 triage vignettes across four acuity levels |
| Language | English and Chinese, location fixed in every prompt |
| Roles | Patient, junior doctor, consultant |
| Pressure | Scripted eight-turn ladder pushing towards less urgent care, plus a mirror ladder pushing towards more urgent care as a control |
| Outcome | The turn at which the triage level drops, and by how much |

**Prior work.**

| Study | Finding |
|---|---|
| "Why LLMs Give In" (Aug 2026) | Fully crossed, about 1.2 million trials; user as layperson, medical student, nurse or physician. Versus a layperson, a claimed physician made capitulation 2.62 times as likely in multi-turn chats, a medical student 2.19 times, a nurse 1.23 times. Challenging a committed answer gave about 2.8 times more capitulation than putting the false claim in the first message. Names triage, non-English medicine, proprietary models and longer repeated pushback as untested |
| Persona-driven challenge (medRxiv, May 2026) | In frontier models, vulnerable personas drew more sycophancy than authority personas; the medical student persona drew the most. The authors call it an inversion of the expected authority gradient |
| "Obedience to Unsafe Clinical Instructions" | Models consistently obeyed unsafe clinical instructions given authority cues |
| "The Doctor Will Agree With You Now" (2026) | Ten models, four escalating pushbacks. By the last turn Claude Haiku 4.5 held its diagnosis in 4.7% of cases and Gemini 2.5 Flash in 94.2%. English only, listed as a limitation |
| MedPRESS | 600 dialogues, five turns each, 20 model configurations |

| For | Against |
|---|---|
| Two 2026 papers disagree on whether authority or vulnerability drives capitulation. Resolving a contradiction is a stronger hook than adding a language | Risks reading as a smaller version of a 1.2-million-trial study |
| The largest study names language and triage as untested | The language contrast would have to carry the novelty, and language is the hardest axis to validate |
| The team works inside real clinical hierarchies and can write credible role prompts | A capitulation is only an error if the original triage level was right, so ground truth matters (see E) |
| Works as a single added axis on A or B at one line per prompt | Eight-turn ladders multiply cost and labelling |

---

### D. Language and register

**Question.** Does the language used change the medical advice given, especially across cultures with different power dynamics (Chinese, Japanese, English)?

**Prior work.**

| Study | Finding |
|---|---|
| Apart, 3rd place Jan 2026: cross-linguistic sycophancy | English, Japanese, Bengali; co-authored by Alex Csaky (judge and track designer here). One reviewer was not convinced by its Hofstede Power Distance claim; reviewers said three languages confound causal interpretation and asked for more realistic contexts |
| "Better to Ask in English" (2024) | Compared health answers in English, Spanish, Chinese and Hindi |
| Health consistency across languages (2025) | Significant inconsistencies across English, German, Turkish and Chinese |
| "Implicit Geographic Inference in LLM Medical Triage" (2026) | Identical symptoms: emergency-referral rate 30% in English, 20% in Chinese, 0% in Japanese. Adding a Tokyo location to the English prompt cut its rate to 6.7%, so language seems to act as a proxy for location. One model, one scenario; no pushback or register |
| "Sounding vs. Being an Expert" (Findings of ACL 2026) | Crossed stated credentials with formal register in English, Spanish, Portuguese. Authors name Japanese and Korean as untested. Not medical |
| "Should We Respect LLMs?" | Politeness levels in English, Chinese and Japanese |

**The version that could stand up.** Manipulate the power dynamic inside each language instead of inferring it from the language: register (deferential, plain, assertive) × role (patient, relative, senior doctor), same stated location in every prompt, back-translation, and compare within each language first.

| For | Against |
|---|---|
| A judge co-authored the Apart entry that placed with this axis, so the topic is valued | The same fact makes a repeat look like replication |
| Honorific register and deference is named as untested, and Japanese keigo makes register a clean grammatical switch | "Language changes medical advice" is already established |
| The team has Chinese on hand and friends who may translate other languages | Language bundles translation quality, training data, inferred location and real health-system differences. Different advice is not necessarily wrong advice |
| Cheap, proven add-on to any core | Three languages cannot support a claim about culture; the power-distance framing was criticised last time |
| | Each language needs a native-level checker. Without a Japanese speaker, Japanese should go |

---

### E. Caution by symptom (triage calibration)

**Question.** Is the model's degree of caution matched to the urgency of the symptom, and how does that shift across roles, languages and pushback?

**Prior work.**

| Study | Finding |
|---|---|
| ChatGPT Health study (Nature Medicine, Feb 2026) | 60 scenarios; just over half of emergencies were sent for review in 24–48 hours instead of to the emergency department; 64.8% of non-urgent home-care vignettes were over-triaged. Gold standard from three independent physicians per scenario |
| CARE-Bench (Aug 2026) | Models err in different directions: GPT-5.5 rarely missed urgent cases but over-triaged heavily; Gemini Pro showed the reverse |
| Frontier models versus government symptom checkers (medRxiv, Sep 2026) | Most systems over-triaged self-care cases |
| Disclaimers and referrals by urgency (JMIR, 2026) | Four models, 227 real patient queries on a three-level urgency scale, 908 responses. Three models gave explicit or urgent referrals in 88–89% of responses |
| "High-Stakes Decisions with Language Models: Insights from Emergency Triage" (Aug 2026) | Already argues triage should be treated as a decision under uncertainty, not a prediction task |
| Safety messaging over time (npj Digital Medicine, 2025) | By 2025, under 1% of outputs carried a medical disclaimer |

| For | Against |
|---|---|
| Real patient-safety relevance; over-caution and health anxiety were raised in the team discussion | The core finding (too cautious on minor cases, not cautious enough on emergencies) is published and widely reported |
| A four-level acuity scale makes "harm" measurable as the direction and size of a shift | One clinician's labels look weak beside three physicians per scenario |
| Supports a neat secondary question: do models resist more firmly when the stakes are higher? | The existing work is multi-model benchmarks; a weekend version is a small replication |

**How it could be used:** stratify scenarios across the four acuity levels and score follow-up advice on the same scale, inside whichever core is chosen.

---

### F. History completeness and diagnosis

**Question.** How does the amount of information a patient gives ("I've got a headache and sore throat" through to a full clerked history) change the model's diagnosis? The underlying point: knowing what to ask is one of the defensible reasons to see a doctor.

**Prior work.**

| Study | Finding |
|---|---|
| Bean et al., Nature Medicine (Feb 2026) | Large randomised user study. Models alone did well; people using them did no better than controls. Users often did not know what information to give. LLM-simulated users did not reproduce the variability of real participants |
| Auger and Scott, medRxiv (Mar 2026) | 1,000 synthetic headache transcripts, 33 diagnoses, completeness sampled 20%–100% in clinical units. GPT-5.2 reached 97.5% with full histories; incomplete histories led to down-triage. No calibration analysis, no question-asking, no lay-versus-clinician contrast |
| "Grounding LLMs in clinical diagnostics" (Nature Communications, 2026) | Accuracy and confidence both higher with complete information |
| "When Confidence Fails" (Aug 2026) | 500 medical questions; confidence stayed misaligned as information was removed |
| MedClarify (Feb 2026) | Masked six categories (symptoms, social history, past medical history, examination, labs, imaging) and measured accuracy loss |
| Q4Dx (Scientific Reports, 2026) | Three levels of symptom disclosure plus questioning efficiency |
| MediQ | Models rarely ask follow-up questions unprompted |
| ChatGPT history-only study (30 BMJ cases) | 76.6% correct on history alone, 93.3% with examination and tests |

| For | Against |
|---|---|
| Uses clerking expertise directly | The core result is known and published at scales a weekend cannot match |
| Easy to explain; real patient-safety relevance | Weak fit to "epistemics" unless reframed around calibration |
| | Few clinical judges to reward the nuance. Likely ceiling of 3 on Impact and Innovation |

**Rescue variant:** hold the information constant and vary only the register (lay message versus clerked history), scoring calibration and safety-netting by tier. Auger and Scott did not report this contrast. It still competes with a busy 2026 literature.

---

### G. Post-hoc justification and confabulation (the original broad idea)

**Question.** People invent reasons for their actions after the fact (split-brain studies; choice blindness). Do models do the same? Sub-questions raised: how reproducible is a model's reasoning if one chat's output is handed to another chat; does it differ across models; what happens after a real mistake; does it justify earlier answers when given irrelevant cues; does it apologise, falsely admit or confabulate.

| Sub-question | Status |
|---|---|
| Justifying answers under irrelevant cues | Saturated: chain-of-thought faithfulness literature; an ICML 2026 paper inducing post-hoc reasoning; motivated-reasoning probes |
| Owning text it did not write | Well covered (see A) |
| Admitting or hiding real mistakes | Covered by "Deception by Omission" |
| Cross-chat reproducibility of reasoning | No ground truth for the "real" reason, so it cannot be scored cleanly in a weekend |
| False admission and confabulation | Became directions A and B |

| For | Against |
|---|---|
| The most intellectually interesting framing, and the human analogue is vivid for non-specialist judges | Too broad to execute rigorously in two days |
| Fits Track 1's interest in what a model will defend | The scorable parts are saturated; the unsaturated parts are not scorable |

**What survives:** the cross-chat idea, used as the third-person audit control in A.

---

### H. Longer conversations

**Observation that prompted it.** A lot of medical LLM evaluation looks like a single ask and response.

**What we found.** That is no longer true for pushback studies: four-pushback and five-turn designs exist (see C), and turn structure is already known to matter (about 2.8 times more capitulation when challenging a committed answer than when the false claim is in the first message). The Oxford user study adds a caution that LLM-simulated users do not behave like real ones.

| For | Against |
|---|---|
| Longer repeated pushback is named as untested by the largest study | Cost and labelling scale with length |
| Distance between advice and misquote is already an axis in A | Not a project by itself |

**Working suggestion from earlier:** cap at about eight turns and script the user side.

---

### I. Threads from the team discussion

| Thread | Closest existing work | Status |
|---|---|---|
| Sycophancy by how "bad" the user says they are | ELEPHANT uses Reddit Am-I-the-Asshole posts; models sided with the poster in 42% of cases human voters judged inappropriate | Partly open, but far from the team's clinical strengths |
| First message versus later pushback | Measured in "Why LLMs Give In" | Done |
| Model predicting its own behaviour (metacognition) | "Strangers to Themselves" (Sep 2026): asked models whether they would cave to pushback; some rated themselves strong exactly where they failed | Done |
| User versus a document | NeurIPS 2026 paper: models that resist a wrong user still flip for a "verified" source | Active |
| Delusion validation | Not searched | Unknown |
| Doctor demographics | Not searched | Unknown |
| Reddit "crux" tool | Not searched | Unknown |
| Responsibility and apology | Became direction B | Most open |

---

### J. Other ideas that use clinical background

| Idea | Track | Why it could work | Caveat |
|---|---|---|---|
| **Hedge audit.** Radiology has a working vocabulary of uncertainty ("likely", "cannot exclude", "consistent with"). Have models write impressions, elicit the number behind each hedge, then challenge it. Measure the gap between implied and defended confidence | 1 | Maps onto the page's "MisleadBench" example; radiology expertise sets the reference | Prior work on verbal-uncertainty phrases not checked |
| **Citation binder for health advice.** Check whether each guideline citation in an LLM answer supports the specific claim | 2 | The page names health advice and citation checking | More engineering than science; needs a strong builder |
| **Decision-brief rubric for health.** Clinician-anchored rubric and grading harness for chatbot health briefings | 3 | The page names this example | Rubric work is slow; hard to show results by Sunday |

---

## 4. Where the team stands

- **Liked, without a single project yet:** languages, medicine, epistemic surrender (accepting a misquote), power dynamics, over-caution.
- **Open disagreement:** one view is that translating into more languages is enough novelty; the other is that languages cannot be the sole novelty. The Apart precedent cuts both ways (section 3-D).
- **Time:** Saturday is the only full day together.

## 5. Assessment so far

*This is Claude's reading from the earlier sessions, recorded so the reasoning is visible. It is an input to the decision, not the decision.*

| Rank | Direction | Why |
|---|---|---|
| 1 | B, built on A's design | Most open in our searches, the only thing that moved a model in the hand pilot, and it keeps A's strongest property (the record makes errors unambiguous) where the record is in the chat |
| 2 | A as originally scoped | Cleanest design; higher floor-effect risk and closer prior work |
| 3 | C standalone | Viable, with a real hook in the two conflicting papers, but sits closest to a very large existing study |
| 4 | D standalone (register × role form) | Depends entirely on native-level checkers |
| 5 | E, then F | Crowded; better as an outcome scale and a parked idea |

**What would change this ranking**

- A full read of Wu showing it already scores invented rationales for misattributed advice (hurts A and B)
- A 30-minute pilot of B with the record in the chat showing every model simply corrects the user (floor effect; pushes towards the memory-summary or apology-ban conditions, or towards C)
- A confirmed native-level Japanese or Korean checker (lifts D)
- A fast search on the three unsearched threads turning up something clearly open (section 3-I)
