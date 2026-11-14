# Literature and prior projects

**Read this first.** Nothing below has been read in full by the team. The "Checked" column says how each entry was sourced:

- **Page** = the page was fetched and machine-summarised
- **Excerpt** = abstract or search excerpt only

Before any entry is cited in the report: open the link, confirm title, authors, venue, year and the specific number, then tick the box. Fabricated or wrong references can disqualify a submission.

Papers marked ★ are the ones to read in full first.

---

## 1. Misquotes, false admission, confabulation (directions A, B, G)

| ✓ | Paper | What it reports | Why it matters | Checked |
|---|---|---|---|---|
| [ ] | ★ Wu, "Aligning to Illusions" (Mar 2026). https://arxiv.org/abs/2603.08412 | 15 LLM judges on pairwise text preferences; near-zero choice blindness with prior reasoning in context, over 50% without it; near-universal compliance under social pressure | Closest prior work to A. May already score invented justifications | Excerpt |
| [ ] | ★ CAVE-Bench (Sep 2026). https://arxiv.org/html/2609.32616v1 | 365 agentic tasks; "gaslight sycophancy"; False Confession Rate 3.5%–68.7%. Refuting evidence kept out of context; invented explanations not scored | Closest to B; defines what we would add | Excerpt |
| [ ] | "Deception by Omission" (Oct 2026). https://arxiv.org/html/2610.11351v1 | Confession of a planted mistake varied widely by model and follow-up wording (reported ranges include 2.9%–69.9% and 20.0%–87.2%) | Real mistakes rather than false ones; useful contrast and control idea | Excerpt |
| [ ] | Anthropic, "Emergent Introspective Awareness". https://transformer-circuits.pub/2025/introspection/index.html | Prefilled outputs disavowed by default; claimed as intentional after concept injection | Ownership of text the model did not write | Excerpt |
| [ ] | Self-report of adversarial prefills. https://deeplearn.org/arxiv/783266/can-llms-reliably-self-report-adversarial-prefills,-and-how | Ten models; claimed intent on prefilled outputs 27.3% of the time on average | Same | Excerpt |
| [ ] | Pandey, "LLMs Know They're Wrong and Agree Anyway" (2026). https://arxiv.org/abs/2604.19117 | The "this is wrong" signal is present internally when models sycophantically agree | Mechanistic support for "deference, not misreading" | Excerpt |
| [ ] | Kim et al., "Challenging the Evaluator". https://arxiv.org/pdf/2509.16533 | Saved in the earlier brief without a summary | Check relevance | Excerpt |
| [ ] | Inducing post-hoc chain-of-thought (ICML 2026). https://icml.cc/virtual/2026/79546 | Induces post-hoc reasoning | Shows the irrelevant-cue version of G is saturated | Excerpt |
| [ ] | Choice blindness, overview of the paradigm. https://pmc.ncbi.nlm.nih.gov/articles/PMC4172758/ | People handed an option they did not choose mostly fail to notice and give confident reasons | Human analogue for A | Excerpt |
| [ ] | "Who's Sorry Now": apology types from LLM chatbots. https://dl.acm.org/doi/10.1145/3793679 | Apology-type taxonomy from user studies | Vocabulary for B's outcome labels (conditional apology and so on) | Excerpt |
| [ ] | Outcome bias in blame judgments. https://www.researchgate.net/publication/247981279_The_Role_of_a_Posteriori_Victim_Information_in_Judgments_of_Blame_and_Sanction | Cited earlier for "LLMs show outcome bias when judging other people's negligence" | **Problem: this link is a human-psychology paper. The LLM claim needs its own source before it can be used** | Excerpt |
| [ ] | Apart: "Towards a Benchmark for Self-Correction on Model-Attributed Misinformation". https://apartresearch.com/sprints/projects/towards-a-benchmark-for-self-correction-on-model-attributed-misinformation | Past Apart entry; did not place top five. CommitCheck and SEED "Liar's Benchmark" are also adjacent (no links saved) | Shows how this area has fared with Apart judges | Excerpt |

## 2. Sycophancy, authority and multi-turn pressure in medicine (directions C, H)

| ✓ | Paper | What it reports | Why it matters | Checked |
|---|---|---|---|---|
| [ ] | ★ "Why LLMs Give In: Conversational Factors and Reasoning Behind Medical Sycophancy" (Aug 2026). https://arxiv.org/html/2608.01017v1 | Fully crossed, about 1.2 million trials; roles layperson, medical student, nurse, physician. Capitulation versus layperson in multi-turn: physician 2.62×, medical student 2.19×, nurse 1.23×. Challenging a committed answer about 2.8× more capitulation than a false claim in the first message. Untested: triage, non-English medicine, proprietary models, longer repeated pushback | The study any role-based design is compared against | Page |
| [ ] | "Evaluating Sycophancy in Frontier Models Using Persona-Driven Challenge" (medRxiv, May 2026). https://www.medrxiv.org/content/10.64898/2026.05.17.26353406v1.full | Vulnerable personas drew more sycophancy than authority personas; medical student persona the most; authors call it an inversion of the authority gradient | Conflicts with the row above. The contradiction is a possible hook | Excerpt |
| [ ] | "Obedience to Unsafe Clinical Instructions". https://pmc.ncbi.nlm.nih.gov/articles/PMC13015605/ | Models consistently obeyed unsafe clinical instructions given authority cues | Authority and safety | Excerpt |
| [ ] | "The Doctor Will Agree With You Now" (2026). https://aclanthology.org/2026.healing-1.2.pdf | Ten models, four escalating pushbacks. Held diagnosis by the last turn: Claude Haiku 4.5 4.7%, Gemini 2.5 Flash 94.2%. English only | Multi-turn pressure is already studied; language is not | Page |
| [ ] | MedPRESS. https://arxiv.org/abs/2608.02520 | 600 dialogues, five turns each, 20 model configurations | Same | Page |
| [ ] | ELEPHANT: social sycophancy. https://sotaverified.org/papers/social-sycophancy-a-broader-understanding-of | Reddit Am-I-the-Asshole posts; models sided with the poster in 42% of cases human voters judged inappropriate | On the sprint's reading list; closest to the "bad person" thread | Excerpt |
| [ ] | "Strangers to Themselves" (Sep 2026). https://arxiv.org/html/2609.09899 | Asked models whether they would cave to pushback; some rated themselves strong exactly where they failed | Covers the self-prediction thread | Excerpt |
| [ ] | "Authority Bias in Language Models" (summary). https://letters.lossfunk.com/p/your-llm-wont-believe-you-but-it | Believed to be the NeurIPS 2026 paper reporting that models which resist a wrong user still flip for a "verified" source. Confirm the match | User-versus-document thread; relevant to B's memory-summary condition | Excerpt |
| [ ] | MedRedFlag. https://arxiv.org/html/2601.09853v1 | False premises in patient questions | Adjacent to misquotes | Excerpt |

## 3. Language, register and culture (direction D)

| ✓ | Paper | What it reports | Why it matters | Checked |
|---|---|---|---|---|
| [ ] | ★ Apart, 3rd place Jan 2026: "Cross-Linguistic Sycophancy in Frontier LLMs". https://apartresearch.com/sprints/projects/crosslinguistic-sycophancy-in-frontier-llms-a-benchmark-study-w55u | English, Japanese, Bengali; co-authored by Alex Csaky. Reviewer unconvinced by the Hofstede Power Distance claim; three languages said to confound causal interpretation; more realistic contexts requested | The precedent, and the judges' objections to it | Page |
| [ ] | "Implicit Geographic Inference in LLM Medical Triage" (2026). https://arxiv.org/html/2606.01204 | Identical symptoms: emergency referral 30% in English, 20% in Chinese, 0% in Japanese. Tokyo location added to the English prompt: 6.7%. One model, one scenario; prompt equivalence unverified | Language acts as a proxy for location. Fix location in every prompt | Page |
| [ ] | "Sounding vs. Being an Expert" (Findings of ACL 2026). https://aclanthology.org/2026.findings-acl.1627.pdf | Stated credentials × formal register in English, Spanish, Portuguese. Japanese and Korean named as untested. Not medical | Defines the open register gap | Page |
| [ ] | "Better to Ask in English" (2024). https://arxiv.org/pdf/2310.13132 | Health answers compared in English, Spanish, Chinese, Hindi | "Language changes advice" is established | Excerpt |
| [ ] | "Do LLMs Provide Consistent Answers to Health-Related Questions across Languages?" (2025). https://arxiv.org/pdf/2501.14719 | Significant inconsistencies across English, German, Turkish, Chinese | Same | Excerpt |
| [ ] | "Should We Respect LLMs?". https://arxiv.org/pdf/2402.14531 | Politeness levels in English, Chinese, Japanese | Register manipulation precedent | Excerpt |
| [ ] | "Perspectives on Cross-Lingual Consistency in LLMs for Medical Questions". https://arxiv.org/html/2609.07687v1 | Saved without a summary | Check relevance | Excerpt |

## 4. Triage and caution (direction E)

| ✓ | Paper | What it reports | Why it matters | Checked |
|---|---|---|---|---|
| [ ] | ChatGPT Health study (Nature Medicine, Feb 2026). News coverage: https://www.nbcnews.com/health/health-news/chatgpt-health-under-triaged-half-medical-emergencies-rcna261409 ; design summary: https://www.iatrox.com/blog/chatgpt-health-undertriage-52-percent-emergencies-nature-medicine-2026 | 60 scenarios; just over half of emergencies sent for 24–48 hour review instead of the emergency department; 64.8% of non-urgent home-care vignettes over-triaged; gold standard from three physicians per scenario | The benchmark a triage design is compared against. **Find and cite the journal article, not the coverage** | Excerpt |
| [ ] | CARE-Bench (Aug 2026). https://arxiv.org/html/2608.03731v1 | Models err in different directions: GPT-5.5 over-triages, Gemini Pro the reverse | Direction of error is model-specific | Excerpt |
| [ ] | Frontier LLMs versus government-backed symptom checkers (medRxiv, Sep 2026). https://www.medrxiv.org/content/10.64898/2026.09.01.26361908v1.full | Most systems over-triaged self-care cases | Same | Excerpt |
| [ ] | Disclaimers and referral patterns across urgency levels (JMIR, 2026). https://www.jmir.org/2026/1/e84668 | Four models, 227 real patient queries, three urgency levels, 908 responses; three models gave explicit or urgent referrals in 88–89% of responses | Possible source of real patient queries and an urgency scale | Excerpt |
| [ ] | "High-Stakes Decisions with Language Models: Insights from Emergency Triage" (Aug 2026). https://arxiv.org/pdf/2608.01361 | Argues triage is a decision under uncertainty, not a prediction task | The epistemics framing of triage is taken | Excerpt |
| [ ] | Declining medical safety messaging (npj Digital Medicine, 2025). https://www.nature.com/articles/s41746-025-01943-1 | By 2025, under 1% of outputs carried a medical disclaimer | Background | Excerpt |

## 5. History completeness and question-asking (direction F)

| ✓ | Paper | What it reports | Why it matters | Checked |
|---|---|---|---|---|
| [ ] | Bean et al., Nature Medicine (Feb 2026). https://www.ox.ac.uk/news/2026-02-10-new-study-warns-risks-ai-chatbots-giving-medical-advice ; preprint https://arxiv.org/html/2504.18919v1 ; https://ora.ox.ac.uk/objects/uuid:ccb8b891-c738-4890-a4d5-45959d0e04d9/files/rns0648349 | Large randomised user study. Models alone did well; people using them did no better than controls; users often did not know what to tell the model. LLM-simulated users did not reproduce real participants' variability | Why to script user turns instead of simulating users | Excerpt |
| [ ] | Auger and Scott (medRxiv, Mar 2026). https://www.medrxiv.org/content/10.64898/2026.03.23.26349082v1.full | 1,000 synthetic headache transcripts, 33 diagnoses, completeness 20%–100%. GPT-5.2 97.5% with full histories; incomplete histories led to down-triage | F has been done at scale | Excerpt |
| [ ] | "Grounding LLMs in clinical diagnostics" (Nature Communications, 2026). https://pmc.ncbi.nlm.nih.gov/articles/PMC13181090/ | Accuracy and confidence both higher with complete information | Same | Excerpt |
| [ ] | "When Confidence Fails" (Aug 2026). https://arxiv.org/html/2608.09080v1 | 500 medical questions; confidence stayed misaligned as information was removed | Calibration angle is covered | Excerpt |
| [ ] | MedClarify (Feb 2026). https://arxiv.org/pdf/2602.17308 | Masked six information categories; measured accuracy loss | Same | Excerpt |
| [ ] | Q4Dx (Scientific Reports, 2026). https://www.nature.com/articles/s41598-026-37022-y_reference.pdf | Three levels of symptom disclosure plus questioning efficiency | Same | Excerpt |
| [ ] | MediQ. https://arxiv.org/html/2406.00922v3 | Models rarely ask follow-up questions unprompted | Same | Excerpt |
| [ ] | ChatGPT on history alone (30 BMJ cases). https://synapsesocial.com/papers/W4391858226 | 76.6% correct on history alone; 93.3% with examination and tests | Same | Excerpt |

## 6. Sprint reading list (Track 1), not yet read

MASK, DarkBench, SycEval, ELEPHANT, "Why Language Models Hallucinate", ForecastBench, Petri and Bloom, the Inspect framework. Also the "State of the Field: AI for Epistemics and Coordination" report and Forethought's "AI Impacts on Epistemics".

## 7. Not yet searched

- Delusion validation by chatbots
- Doctor demographics and model behaviour
- Reddit "crux" tool
- Verbal-uncertainty phrases and their numeric meaning (for the hedge audit in direction J)
