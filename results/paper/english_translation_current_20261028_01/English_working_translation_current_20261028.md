# English working translation of the current manuscript

**Status:** Complete working translation of the manuscript text based on the authoritative Chinese candidate dated 2026-10-28. The Word draft is not submission-ready: source figures and tables require visual review in the English layout, citations need final verification, and author metadata and the target-journal template remain outstanding.

# Controlled Evaluation and Evidence-Coverage Analysis of Dual-Source Retrieval-Augmented Generation over Annual Reports and Regulations

## Abstract

Listed-company evaluation requires both annual-report disclosures and relevant regulatory evidence. This study asks whether source-separated retrieval improves answer ratings and evidence supply in question answering over annual reports and regulations. We build a dual-source retrieval-augmented generation (RAG) workflow that preserves document identity and source locations. Using 60 questions about the 2024 annual reports of 20 companies, we compare merged retrieval with dual-route retrieval, and separately test source-role prompting while reusing exactly the same dual-route context. The primary comparison planned 180 Kimi-provider requests; 147 first-pass outputs were structurally valid. Thirty-three responses later written in the assistant session did not follow the frozen prompt or API protocol; 31 had entered the earlier scoring file and all 33 are now excluded. After filtering, 355 of 400 provider-generated outputs remain with two-rater scores. For 41 observed G1/G2 pairs, G2 has a company-macro mean difference of 0.228 on a 0–8 scale (20,000 company-clustered bootstrap replications; pointwise 95% interval [0.110, 0.355]); however, the all-question missing-outcome bounds include zero. For 38 observed G2/G3 pairs, the difference is 0.013 (observed-pair interval [0.000, 0.039]). Dual-route retrieval increases the co-occurrence of annual-report and regulatory sources in assembled contexts from 68.3% to 100%, but does not improve mean coverage of designated evidence locations across the two source types; regulatory reference-location coverage remains limited. The observed total-score difference is concentrated in the regulatory-evidence dimension, while citation and uncertainty dimensions show ceiling effects. These findings apply only to the present sample, model, and rating protocol.

**Keywords:** retrieval-augmented generation; annual reports; regulatory evidence; provenance; context-budget replay; human evaluation

## 1 Introduction

Evidence used in listed-company evaluation has distinct roles. Annual reports record companies’ public disclosures about governance arrangements, internal-control matters, and dividend policies. Regulations specify requirements that relevant entities are expected to meet. The evidence needed to answer “What did the company disclose?” differs from that needed to answer “Does the disclosure satisfy the applicable requirement?” The former cannot be inferred from regulations alone, and the latter cannot be established from a company’s own description alone. Organizing both types of evidence into a verifiable answer is a concrete information-processing problem for professional document question answering.

Conventional retrieval often places passages in a single ranked list according to their relevance to a query, but semantic similarity does not encode the evidentiary role a passage should play in an argument. When a regulation ranks highly because it contains terminology closely matching the question, company-specific disclosures may be pushed out of the context; conversely, a policy summary in an annual report may displace the normative text itself. A limited context window intensifies this competition among candidates. Even if the final answer mentions both the company and a regulation, that alone does not establish that the model retrieved and correctly used the original evidence from both sources.

Retrieval-augmented generation (RAG) combines external retrieval with language generation, providing an updateable evidence interface for knowledge-intensive tasks [1]. However, retrieval relevance, context availability, claim support, and regulatory applicability are distinct questions. Adding a reranker, asking the model to cite each claim, or introducing multiple roles may change an answer, but the value of each component must be tested under comparable conditions on the same questions. We therefore treat source separation and role prompting as two distinct interventions.

This study focuses on two research questions. **RQ1:** Given the same questions, corpus, and generation configuration, does source-separated retrieval improve answer ratings and auditable evidence supply relative to merged retrieval? **RQ2:** When the retrieved context is identical, does source-role prompting provide additional rating gains? Source-removal and same-family service-version comparisons are retained as exploratory contrasts in the main text. Candidate-budget replay and retrieval-location diagnostics from a fresh BM25 run are reported in Supplementary Materials S1–S2. These analyses are not treated as independent research questions or as evidence for general claims.

Our contributions are threefold. First, we construct a dual-source RAG workflow that preserves document identity, physical locations, and records of the actual prompts. Second, we compare merged retrieval (G1), dual-route retrieval (G2), and source-role prompting with identical retrieved evidence (G3), separating retrieval organization from prompting. Third, using 60 questions from 20 companies and two-rater scores, we report company-clustered paired analyses and distinguish source availability, target-location coverage, and answer ratings. We do not present a combination of existing components as a new retrieval algorithm, nor do we treat valid citation identifiers as a substitute for semantic support.

In the controlled comparisons, dual-route retrieval shows a positive score difference relative to merged retrieval, whereas role prompting with the same context shows no stable gain. We discuss the relationship between source organization and evidence coverage while limiting the findings to this sample, model configuration, and rating protocol. Exploratory contrasts for no-reranking, saved BM25 generations, source removal, and same-family service versions remain in the main-text results; budget replay and fine-grained diagnostics from the fresh BM25 retrieval run are placed in Supplementary Materials S1–S2. Figure 1 presents the system workflow.

**Figure 1.** System workflow and replayable records. Annual reports and regulations are assigned separate retrieval scopes. Retrieval, reranking, and whole-chunk budget packing produce the actual context. Source coordinates do not establish semantic support.

## 2 Related Work and Research Positioning

### 2.1 Financial Document Question Answering and Domain Evidence

FinQA focuses on numerical reasoning over financial data [2], while TAT-QA studies question answering over hybrid tabular and textual content [3]. These benchmarks show that evidence in financial reports differs structurally from general open-domain text, but their objectives are not equivalent to jointly evaluating company disclosures against normative requirements. HiREC applies hierarchical retrieval and evidence curation to standardized financial documents [4], demonstrating prior work on long-document organization and supplementary querying.

Recent annual-report QA benchmarks further evaluate the joint organization of tables, prose, and answer evidence. ARQA covers ten fiscal years of automotive-company annual reports and provides approximately 2,500 lookup, calculation, and insight questions; the questions were checked and recalculated deterministically and reviewed by domain experts [28]. The Chinese CFQA benchmark comprises 500 questions based on the 2023–2025 annual reports of 50 listed companies, with human-annotated answers linked to source text; it compares RAG with a no-retrieval baseline and distinguishes answer matching from evidence support and fabrication [29]. Cheng et al. propose CFinRAG, which builds a financial event knowledge graph from Chinese financial research reports and combines query reconstruction with two-level retrieval; it is evaluated on 1,200 reports and 3,600 QA pairs [30]. These studies focus, respectively, on question answering within annual reports and graph-based financial event reasoning. We study the joint evaluation of company disclosures and independent regulatory evidence, comparing source-separated with merged retrieval on 60 questions from 20 companies while separately examining role prompting. We do not claim financial-document retrieval, annual-report QA benchmarks, or financial knowledge-graph construction as standalone innovations.

Siddharth and Luo extract explicit facts from engineering documents for use in generation [5], while Yang et al. survey the integration of language models with knowledge-based methods [6]. We instead use documents and their locations directly as runtime inputs, avoiding the need to first build an exhaustive company-fact database. Reference facts and evidence are used for offline evaluation rather than encoding answers into the runtime knowledge base in advance. This design allows retrieval, parsing, and generation errors to be examined separately.

### 2.2 Sparse and Dense Retrieval and Domain Adaptation

BM25 provides a sparse retrieval signal based on term matching [7], while methods such as DPR learn dense representations to mitigate lexical mismatch [8]. The Qwen3 Embedding series provides additional embedding and reranking models [9]. Complementarity among retrieval signals does not imply improved end-to-end quality in every domain. Score scales, candidate composition, and the downstream generator can all affect outcomes; we therefore retain BM25-only and no-reranking conditions. Reciprocal rank fusion (RRF) offers a rank-based fusion approach [10], but the primary configuration in this study uses fixed weighted fusion, and we do not report unrun RRF results as experimental findings.

Alier et al. address acronym retrieval failures in educational corpora by studying query-time and ingestion-time augmentation, including component effects, errors, and deployment costs [11]. This domain-specific work suggests first identifying an actual retrieval failure and then testing the intervention that targets it. Our domain-specific factor is that the two document types play different evidentiary roles. The added replay analyses measure changes in evidence supply and do not interpret location matches as complete semantic support.

### 2.3 Iterative Retrieval and Agent Collaboration

Self-RAG improves evidence use through retrieval and self-reflection [12]; CRAG introduces corrective processing based on retrieval quality [13]; and Adaptive-RAG selects retrieval strategies according to question complexity [14]. AIR-RAG studies iterative retrieval and alignment with the generator [15]. These methods suggest stronger directions for adaptive baselines, but their training objectives, controllers, and inference workflows cannot be reproduced by simply adding an instruction to “reflect.” We do not reproduce these trained methods; they are discussed as related work and their performance is not inserted into our empirical comparison tables.

ReAct interleaves reasoning with external actions [16]. CoLE develops a collaborative legal prompting framework inspired by teamwork in legal practice [17], while MADKE uses shared external knowledge to support multi-agent debate [18]. Our current implementation is a fixed dual-source retrieval and generation workflow. Source-role prompting is only a prompting intervention; it does not perform autonomous tool planning or multi-agent communication. Making these implementation boundaries explicit prevents the number of modules, sources, and agents from being conflated.

### 2.4 Citation Evaluation and Validity in Professional Tasks

ALCE evaluates generation and citation quality [19]; RAGAs provides automated evaluation methods [20]; and RAGChecker further decomposes retrieval and generation stages [21]. Together, these studies show that surface answer quality and parseable citations alone do not explain overall RAG performance. We report request success, structural validity, source replayability, human quality ratings, and regulatory applicability separately; model-reported support status is not used as a substitute for human judgment.

LegalBench-RAG emphasizes locating relevant evidence spans in legal documents [22], while long-context research shows that information length and position can affect model use [23]. Our current reference labels are primarily at the page and key-point levels; they are not exhaustive passage-level relevance judgments. Accordingly, the added retrieval analyses use strict source-identity and page-location proxies rather than standard Recall or nDCG measures for which the required relevance judgments are unavailable. Determining whether a regulation applies at a particular time also requires evidence about the event date and the applicable regulatory version; retrieval relevance alone cannot establish it. Table 1 summarizes representative work and how this study differs.

**Table 1. Representative studies and their relationship to this study**

| Study | Primary focus | Scope adopted or compared here |
|---|---|---|
| FinQA / TAT-QA [2,3] | Numerical and hybrid-content QA over financial reports | Related tasks; this study focuses on joint disclosure and normative evidence |
| ARQA / CFQA [28,29] | Annual-report table–text QA benchmarks and answer-evidence evaluation | Focus on QA within annual reports; this study adds regulatory source roles and source-organization contrasts |
| HiREC [4] | Hierarchical retrieval and evidence curation for financial documents | Financial retrieval itself is not claimed as a new method |
| Domain-knowledge RAG [5,6,11] | Domain knowledge representation and retrieval augmentation | Component-control lessons are adopted; ontologies and knowledge graphs are not replicated |
| Self-RAG / CRAG [12,13] | Self-reflection or corrective retrieval | Not faithfully reproduced; no performance values are entered in comparison tables |
| Adaptive-RAG / AIR-RAG [14,15] | Adaptive and iterative retrieval | Potential stronger baselines; this study uses fixed retrieval |
| CoLE / MADKE [17,18] | Legal-expert prompting and knowledge-enhanced debate | The current system is not described as multi-agent |
| ALCE / RAGAs / RAGChecker [19–21] | Citation and fine-grained quality evaluation | Structural validity, semantics, and human ratings are distinguished |
| LegalBench-RAG [22] | Evidence-span retrieval in legal documents | Page-level labels here are not presented as exhaustive passage-level qrels |

## 3 Dual-Source Retrieval and Traceable Generation

### 3.1 Inputs, Outputs, and Unit of Analysis

Let *c* denote a company identifier, *y* a report year, and *q* an evaluation question. The public input is *x* = (*c*, *y*, *q*). The document collection consists of annual reports *D*ₐ and regulations *D*ᵣ, and the source function τ(*d*) takes the value A or R. The output contains an answer *a*, a set of substantive claims *C*, links between claims and the evidence identifiers actually provided, and explanations of insufficient or conflicting materials. The unit of evaluation is a document-grounded answer to a given question, not an unconditional rating of a company’s actual governance performance. Table 2 defines the notation.

Annual reports provide disclosure-level evidence about company facts. Failure to parse an item, retrieve it, or find it in the supplied passages does not establish that the item does not exist. Normative claims require checking the regulatory text. Comparing a company disclosure with a regulatory requirement also requires confirming that the entities, topics, and temporal conditions are comparable. When the materials are incomplete, the system may retain an unknown status rather than being forced to return a compliance conclusion.

**Table 2. Notation**

| Symbol | Definition |
|---|---|
| *x* = (*c*, *y*, *q*) | Company, report year, and evaluation question |
| *D*ₐ(*c*, *y*), *D*ᵣ(*q*) | Eligible retrieval scopes for annual reports and regulations |
| *H*ₐ, *H*ᵣ, *H*ₘ | Separate candidate sequences for each source and the merged sequence |
| *K*ₐ, *K*ᵣ, *K* | Per-source candidate quotas and the overall limit |
| *B*, *T(E)* | Reference-token context limit and token-counting function |
| *E*ₘ, *E*ᴅ | Actual contexts assembled by merged and dual-route retrieval |
| *C*, *L* | Set of substantive claims and claim–evidence links |
| *Qᵢ*, Δ꜀ | Exploratory answer-quality total and within-company paired difference |

### 3.2 Document Identity and Location Representation

Each document is registered with its source, company and year, full-text or summary status, version information, and file SHA-256. Annual-report PDFs are represented as text frames by physical page. Each passage retains the file hash, page-text hash, one-based physical page order, and character start and end offsets. Printed page numbers are handled separately from the physical order shown by a PDF reader; page numbers are not inferred from filenames. OCR text retains its parsing provenance and unverified status, and the original PDF remains unchanged.

Regulatory sources are located according to their actual file formats. Text regulations retain the original file hash and character offsets. Sources that can be mapped to a PDF also retain the physical page and within-page location. A provision spanning multiple pages requires locations for the individual passages; a single “correct page number” is not invented for the entire provision. Promulgation, effective, repeal, and event dates are separate fields. Missing values are not filled using local file-modification times or the report year.

Location records allow a reviewer to replay which material the model saw; they do not establish that a passage supports a claim. We treat source parsing as a prerequisite for semantic auditing, not a substitute for it. Matching hashes establish byte-level identity only. Even reliable source text may be unsuitable for a particular evaluation because the entity, time, or exception conditions differ. Table 3 summarizes source-record fields and their validation scope.

**Table 3. Source records and validation levels**

| Record or check | Retained information | What it can establish |
|---|---|---|
| File identity | Source, version, SHA-256 | Association between file bytes and declared identity |
| PDF location | Physical page, text-frame hash, character offsets | Passage can be traced to the actual page |
| Text regulation | File hash, provision number, character offsets | PDF page numbers are not fabricated |
| Context replay | Actual passage IDs, prompt/context hashes | Material actually supplied to the model |
| Citation-ID validation | Whether a citation belongs to the supplied ID set | Structural parseability only |
| Human source-text rating | Facts, regulations, citations, and uncertainty | Exploratory quality judgment |
| Temporal applicability | Event date, validity period, and version | Requires independent evidence; not fully verified here |

### 3.3 Dual-Scope Retrieval and Fixed Fusion

The annual-report scope *D*ₐ(*c*, *y*) is restricted by company and report year. The regulatory scope *D*ᵣ(*q*) is restricted by document type and the treatment of temporal metadata allowed by the actual configuration. Both strategies use the same available source scope, avoiding confounding “adding a correct document” with “changing the ranking method.” The default retrieval model is Qwen3-Embedding-0.6B, and the reranker is Qwen3-Reranker-0.6B. Document encoding does not include a query prompt, and queries use a fixed task instruction. None of the 60 questions included an independent event date. The system did not infer dates from the 2024 report year and retained all 5,994 regulatory passages under an `unknown=retain` rule; zero passages were excluded by temporal filtering. The results therefore cannot be attributed to effective temporal filtering.

Dense and BM25 signals are fused with fixed settings: a dense weight of 0.7 and a sparse weight of 0.3. These are prototype parameters, not weights demonstrated to be optimal on this test set. Candidates are reranked before context assembly. We do not retune these settings based on test results or describe untested weight changes as improvements. In implementation, each channel first retrieves up to 2 × *top-k* candidates. Scores within each returned channel set are divided by that channel’s maximum score (using 1 when the maximum is 0). The union is scored with the 0.7/0.3 weighted sum, and up to 4 × *top-k* candidates are passed to reranking, with `max_length=3072`. The actual candidate count is bounded by the size of the channel union. This is maximum-score normalization, not min–max normalization.

G1 places eligible passages from both source types into a shared candidate pool and takes up to ten candidates according to hybrid retrieval and reranking. G2 retrieves up to five candidates separately from each annual-report and regulatory scope, ranks each side independently, and alternates annual-report and regulatory candidates in that order; after one side is exhausted, candidates from the other side continue. G3 directly reuses the context assembled for G2. The two strategies have the same final total candidate limit, but their internal channel retrieval and reranking workloads are not equivalent. Dual-route retrieval does not guarantee sufficient annual-report evidence for every question because upstream retrieval may fail, passages may be too long, or the total context budget may truncate the candidate set. The added replay experiment measures these conditions directly.

### 3.4 Context Assembly and Comparability

Let the candidate sequence be *H* = (*h*₁, …, *h*ₖ), *T* the frozen reference tokenizer, and *B* the context limit. The assembler visits candidates in the specified order. It retains a candidate if adding the complete passage yields |*T*(*E* ⊕ *hᵢ*)| ≤ *B*; otherwise it skips that passage and continues to the next candidate. Duplicate passage IDs are rejected, passage text is not truncated, and the final record stores retained passages, skip reasons, and the context hash.

This whole-chunk strategy avoids confusing citation locations with truncated fragments, but it can leave some budget unused and change the number of sources in the final context. Candidate quotas are upper limits on what enters the assembler, not guarantees that both source types appear in the final context. If a long annual-report passage is skipped, a shorter regulatory passage later in the sequence may still fit. Such supply changes should be described using actual token counts, passage counts, and location coverage together.

The primary comparison uses a total limit of 6,000 reference tokens. The same limit does not imply the same actual token count or the same provider-side cost; equivalence between the reference tokenizer and the API provider’s tokenizer has not been verified. We therefore define “budget matched” only as sharing a common reference-token limit. The added analyses report actual usage and latency; an equal upper limit is not described as equal computational cost.

G1: *E*ₘ = Packᴮ(Topₖ(*D*ₐ(*c*, *y*) ∪ *D*ᵣ(*q*))); G2: *E*ᴅ = Packᴮ(Merge(Topₖₐ(*D*ₐ), Topₖᵣ(*D*ᵣ))).

G3: *E*ᵣₒₗₑ = *E*ᴅ; *a*₍generic₎ = LLM(*P*₍generic₎, *E*ᴅ), *a*₍role₎ = LLM(*P*₍role₎, *E*ᴅ).

These equations describe the implementation’s control conditions, not an additional training objective. Candidate rankings, passage lengths, and visitation order jointly determine the final context *E*. Thus, even when *K*ₐ = *K*ᵣ, source counts after packing must still be checked.

### 3.5 Citation Constraints and Source Roles

G1 and G2 both require substantive claims to provide the IDs of evidence actually supplied, along with `claims` and `citations`; both also prohibit adding facts or regulations from memory and require limitations to be stated when evidence is insufficient. The difference between G2 and G1 therefore primarily reflects retrieval organization and must not be described as a transition from “no citations” to “citations.” G3 additionally requires factual claims to use annual reports, normative claims to use regulations, and comparative evaluations to have an evidence chain appropriate to both.

The context and source records for G2 and G3 are identical character for character, isolating the incremental effect of the prompt constraint. The model-returned `claims` and `evidence_status` remain model outputs. Structural checks verify required fields, parseable evidence identifiers, and data types; a model-generated `supported` value is not treated as a verified support label. The substantive quality analysis is based on two reviewers’ independent ratings against the source texts.

Source roles can be represented as a claim–evidence bipartite relation. Factual claims link to A-type passages, normative claims link to R-type passages, and comparative claims may link to both. Two links alone do not establish that the comparison is valid: the source passages must also match, support the same issue, and provide adequate evidence for the event date and regulatory version. We did not train a classifier that automatically certifies these relations. Figure 2 illustrates the claim–source relationship and validation levels.

**Figure 2.** Claim–source relations and validation levels. Comparative conclusions require relevant factual and normative evidence, but identifier links alone do not establish semantic support or temporal applicability.

### 3.6 Complexity and Runtime Records

Let *N*ₐ and *N*ᵣ be the candidate counts in the two scopes and *d* the query-vector dimension. Direct similarity computation over cached vectors scales with (*N*ₐ + *N*ᵣ)*d*; BM25 scoring and reranking incur additional costs. G1 and G2 organize candidate pools differently and may therefore involve different upstream retrieval and reranking workloads. An equal final candidate limit does not imply equal retrieval cost. Measured runtime costs in this study come from saved logs; replay time is not treated as neural retrieval time.

The implementation retains layered records of documents, index manifests, input contexts, request parameters, and responses, allowing data changes to be distinguished from inference changes. Full raw responses, structural failures, and one recovery view are retained; API keys are excluded from the paper and material package. Added analyses use new directories and scripts and do not overwrite prior scores, runs, or manuscript versions.

## 4 Data and Experimental Protocol

### 4.1 Document Collection and Questions

We distinguish the system’s searchable document collection from the questions used for scoring. A new retrieval audit identified 13,038 passages from 39 annual reports and 5,994 passages from 87 regulatory sources in the frozen index, for a total of 19,032 eligible passages. These are the actual scopes selected by document type and system-input flags; they are not combined with document or passage counts from earlier pilot runs. The 87 regulatory sources may be text files or PDFs, and physical-page metadata is not available for all of them.

Human evaluation used 60 questions about the 2024 annual reports of 20 companies, with three topics per company: audit committees, internal control, and dividend disclosures. Questions from the same company are related, so the 60 questions are not treated as 60 independent companies. The questions have 180 reference key points, 123 deduplicated reference sources, and 256 question–evidence links. These references are reviewed target passages, not an exhaustive inventory of all supporting evidence. Table 4 summarizes the corpus and annotation scope.

**Table 4. Corpus and annotation scope**

| Object | Quantity | Interpretation |
|---|---:|---|
| Eligible annual-report collection | 39 files / 13,038 passages | 39 source hashes; all have physical-page metadata |
| Eligible regulatory collection | 87 files / 5,994 passages | 87 source hashes; 289 passages have physical-page fields |
| Rated question set | 20 companies / 60 questions | 2024; 20 questions for each of three topics |
| Reference key points | 180 | Question-level scoring criteria, not an exhaustive company-fact database |
| Reference evidence | 123 sources / 256 links | Locations for 122 PDF references and one text reference are present in the index |
| Provider outputs scored in all conditions | 355 answers × 2 raters × 4 dimensions | 2,840 numeric ratings of 0, 1, or 2; 33 session-generated responses are excluded, including 31 that appeared in an earlier scoring summary |

### 4.2 Conditions and Variable Isolation

The primary comparison ran G1, G2, and G3 on all 60 questions, for 180 planned units. G2 and G3 share exactly the same evidence, isolating the prompt constraint. G1 and G2 use the same eligible source scope, total candidate quota, and reference-token limit, although their actual candidate composition and context lengths may differ. The no-reranking and BM25-only conditions each contain 60 units and are retained as retrieval-configuration contrasts.

For source-removal conditions, all annual-report passages or all regulatory passages were deleted from one preselected question per company, for 40 units in total. The text and identifiers of the remaining passages were preserved, and retrieval was not rerun. Because removal changes both information content and context length, this measures the response to a missing source type in the current input; it is not a pure source-role effect or a general noise-robustness test.

The same-family service-version comparison ran three conditions on the same 20 questions, for 60 units. Provider documentation maps `kimi-for-coding` to K2.8 Preview [24], but the underlying checkpoints for the two service aliases have not been independently verified. Neither the K3 nor the `kimi-for-coding` requests included a `reasoning_effort` parameter. Provider documentation dated 2026-10-20 listed their default levels as `high` and `max`, respectively, but the responses did not record a server-side level that could be independently verified. The reasoning budgets were therefore not matched. This comparison cannot be interpreted as an equal-budget comparison of model weights or as cross-provider model-family generalization. Table 5 summarizes the primary and supplementary analyses; Figure 3 illustrates the variable-isolation design.

**Table 5. Scope of the main text and supplementary analyses**

| Analysis | Planned size | Main control and limitation |
|---|---:|---|
| Main comparison | 60 × 3 = 180 answers | G1/G2/G3; count only outputs from frozen provider calls |
| Exploratory retrieval ablation | 60 × 2 = 120 answers | No reranker and BM25 only; not a full factorial design over all configurations |
| Exploratory source removal | 20 × 2 = 40 answers | Delete a source without rerunning retrieval; information and context length both change |
| Exploratory same-family service versions | 20 × 3 = 60 answers | Aliases within one service family; reasoning budget not explicitly matched |
| Supplementary budget replay | 60 × 2 × 3 × 5 = 1,800 contexts | Fixed candidate rankings; not 1,800 newly generated answers |
| Provider-output ratings and robustness diagnostics | 355 outputs / 400 planned units | Excludes 33 session-generated responses; two raters scored the 355 provider outputs |
| Supplementary BM25 rerun | 60 questions × 2 strategies | CPU BM25 over the full eligible scopes; interpreted separately from cached neural candidates |

**Figure 3.** Variable isolation and extended experimental design. Replay varies candidate quotas and packing budgets without changing historical answer scores.

### 4.3 Implementation Parameters and Failed Requests

The retrieval embedding revision was fixed at `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`, and the reranker revision at `e61197ed45024b0ed8a2d74b80b4d909f1255473`. The default was local CUDA with float16 and batch size 1 on a GTX 1660 Ti. File processing, hashing, BM25, and statistical analyses used a general-purpose CPU. Generation used a remote API; local GPU configuration does not determine provider-side generation speed.

The primary generation temperature was 1, the maximum output was 16,384 tokens, the request timeout was 600 seconds, and SDK automatic retries were set to zero. One primary request was made for each question–condition unit. The scheduling seed of 42 was not sent as a generation seed and therefore does not establish exact reproducibility of sampling. Request-setting changes and error receipts caused by provider parameter restrictions or truncation during preparation are retained. Of the 180 first-pass primary-comparison requests, 147 were structurally valid and 33 failed. Another 33 responses were later written by the assistant in the current conversation without the frozen prompt; they involved zero additional provider API calls. Thirty-one had been rated by the two reviewers and two had not. Because their generation source and protocol differed, all 33 were excluded from the controlled comparisons and all-condition statistics.

### 4.4 Two-Rater Scoring and Measurable Outcomes

Two reviewers independently checked each actual answer against the source text. The primary comparison includes only the 147 structurally valid first-pass provider API outputs. After filtering, the full set of experimental conditions contains two-rater scores for 355 provider-generated outputs. The rating dimensions are company facts, regulatory evidence, citation support, and uncertainty handling; each dimension is scored 0, 1, 2, or U. A mean total score is computed only when both raters assign numeric values on all four dimensions: *Qᵢ* = (1/2) Σᵣ Σⱼ *sᵢᵣⱼ*, with a range of 0–8. None of the outputs included in the present scoring contained U. Failed and unrun units are not assigned a quality score of zero. The mean is an analysis measure, not an adjudicated score or a consensus gold label.

Each rating represents an assessment of an answer under the simplified scale used here. It is not a company-governance score or a probability-calibrated compliance accuracy. The citation dimension is a coarse answer-level measure and cannot establish complete attribution for every claim or the joint success rate under the original H1/H2 definitions. Original ratings, review notes, and disagreements are retained; no individual rating was changed in the added analyses.

Scoring the answers is a different process from reviewing the question references. The two existing reviewers of reference materials and the two final answer raters were recorded separately. The project lead corrected an earlier AI-assisted identity label and confirmed that both answer ratings were made by people checking the source text. We follow the acceptance record and do not add an adjudication process that did not occur. The company-macro mean and rater-sensitivity analyses were selected after scores were visible and are therefore exploratory.

### 4.5 Paired Estimation and Missingness Sensitivity

For each question, we match two conditions, calculate the observed paired difference within each company, and then average companies with equal weight. The primary provider-output reanalysis, dimension-level analyses, and topic diagnostics use 20,000 percentile-bootstrap replications with companies as resampling clusters (seed 20261028). We report exploratory pointwise 95% intervals without multiple-comparison adjustment. These intervals condition on observed pairs. Missing pairs are separately bounded over the 0–8 rating scale for all 60 questions; the two summaries have different estimands.

Company clustering accounts for the three related questions within each company but cannot remove cross-company dependence caused by shared regulations. A leave-one-company-out analysis checks whether the observed difference depends on a single company. Complete-question and complete-company analyses examine the direction within jointly successful subsets. None of these resolves all missing-data bias or turns the original questions into an unseen test set.

We also report algebraic bounds for the mean difference over all planned questions. If both scores for a question are known, its contribution is *qₜ − qᵦ*. If the treatment score is missing but the baseline is known, the contribution is in [−*qᵦ*, 8 − *qᵦ*]. If the baseline is missing but the treatment is known, it is in [*qₜ* − 8, *qₜ*]. If both are missing, it is in [−8, 8]. Averaging the summed endpoints across questions gives the sharp bounds while retaining observed one-sided scores. This is a question-weighted range, not a confidence interval for the company-macro mean, and it must not be described as a bootstrap interval.

### 4.6 Evidence Supply and Retrieval Diagnostics

The main text reports source-supply and target-location proxies for the primary experiment only. We use the saved merged/dual Top-10 rankings for 60 questions and compare strict reference-file identities and page numbers, reporting co-occurrence of both source types, source balance, and strict location coverage. Text-file references and PDF page-level references are reported separately. These indicators show whether a candidate or reference location matches; they do not determine semantic support, equivalent substitutes, or regulatory applicability at a historical time. The primary rankings have no question-aligned relevance gold labels. The independent 40-question development-set qrels have no question-ID overlap with the primary experiment; therefore, standard Precision@k, Recall@k, and nDCG@k are not calculated. Candidate-budget replay and fresh BM25 methods and results are reported in Supplementary Materials S1–S2.

## 5 Main Experiment and Rating Diagnostics

### 5.1 Run Coverage and Score Distribution

Of 400 planned provider requests, the primary comparison yielded 147 first-pass outputs, retrieval ablations yielded 109, source-removal conditions yielded 40, and the second same-family service version yielded 59. In total, 355 outputs were structurally valid and received two-rater scores. Another 33 responses were generated within the assistant session; 31 had appeared in the earlier scoring inventory. These responses did not use the frozen Kimi prompt and API protocol and are now excluded. After their exclusion, 45 planned provider units have no eligible output. “Valid” means that the provider returned an output that passed structural checks; it does not mean the facts, citations, or regulatory applicability are correct.

**Table 6. Eligible outputs and two-rater mean scores by condition**

| Condition | Available / planned | Two-rater mean | Rater 1 | Rater 2 |
|---|---:|---:|---:|---:|
| G1 | 52/60 | 7.327 | 7.577 | 7.077 |
| G2 | 47/60 | 7.543 | 7.809 | 7.277 |
| G3 | 48/60 | 7.594 | 7.833 | 7.354 |
| No reranker | 55/60 | 7.809 | 7.855 | 7.764 |
| BM25 | 54/60 | 7.852 | 7.704 | 8.000 |
| No annual report | 20/20 | 6.675 | 7.000 | 6.350 |
| No regulation | 20/20 | 6.925 | 6.850 | 7.000 |
| K2.8 G1 | 20/20 | 7.325 | 7.500 | 7.150 |
| K2.8 G2 | 19/20 | 7.579 | 7.789 | 7.368 |
| K2.8 G3 | 20/20 | 7.600 | 7.850 | 7.350 |

The conditions use different question subsets and have different missingness, so their unpaired means must not be ranked as evidence of method superiority. In particular, service-version and source-removal comparisons use only 20 questions and are not directly comparable with 60-question conditions as full-sample rankings. For the BM25 condition, Rater 2 assigned a perfect score to all 54 outputs, indicating that scale resolution and rater differences require separate examination. Output coverage and two-rater scores by condition are summarized in Table 6.

### 5.2 Incremental Effects of Dual-Route Retrieval and Role Prompting

Among eligible provider outputs, the company-macro difference for the 41 observed G2–G1 pairs was 0.228, with a pointwise 95% interval of [0.110, 0.355] from 20,000 company-clustered bootstrap replications. The G3–G1 difference was 0.289 (42 pairs; [0.158, 0.430]). G3–G2 had only 38 pairs, with a difference of 0.013 ([0.000, 0.039]); one question favored G3, 37 were tied, and none favored G2. Intervals condition on available pairs, are not adjusted for multiple comparisons, and are not preregistered tests. Because G2 and G3 have substantial missingness, positive intervals for observed pairs do not establish a gain across all 60 planned questions; the all-question missing-outcome bounds in Table 10 include zero. Table 7 reports the main paired estimates, and Figure 4 shows rating distributions for the three primary conditions.

The company-macro G2–G1 differences remain positive when the raters are analyzed separately: +0.263 for Rater 1 (company-clustered pointwise 95% interval [0.114, 0.430]) and +0.193 for Rater 2 ([0.096, 0.289]). The corresponding G3–G2 differences are +0.026 ([0.000, 0.079]) and 0.000 ([0.000, 0.000]). These intervals apply only to observed pairs.

**Table 7. Company-macro differences and pointwise 95% intervals for primary and retrieval-baseline comparisons**

| Comparison | Known pairs / planned | Company-macro difference | Pointwise 95% company-clustered interval |
|---|---:|---:|---:|
| G2 − G1 | 41/60 | 0.228 | [0.110, 0.355] |
| G3 − G2 | 38/60 | 0.013 | [0.000, 0.039] |
| G3 − G1 | 42/60 | 0.289 | [0.158, 0.430] |
| G3 − no reranker | 45/60 | −0.222 | [−0.310, −0.130] |
| G3 − BM25 | 45/60 | −0.245 | [−0.343, −0.157] |

**Figure 4.** Provider-output ratings and rater differences across the three primary conditions. Means and pointwise 95% intervals use available outputs only; intervals are clustered by company.

### 5.3 Dimension-Level Analysis

For paired provider outputs, the company-macro G2–G1 differences by dimension were −0.009 for company facts, +0.237 for regulatory evidence, 0.000 for citation support, and 0.000 for uncertainty handling; the total-score difference was +0.228. The observed total-score difference is therefore concentrated in the regulatory-evidence rating. It must not be recast as a general improvement across all dimensions or as improved accuracy in determining temporal applicability.

A near-zero total-score difference between G3 and G2 does not mean that the model behaved identically on every question. Prompting may change the claims and citation structure without changing the reviewers’ coarse ratings. The added analysis separates these output-form changes from semantic quality, so that more citations or a longer answer are not treated as evidence of greater accuracy. Table 8 and Figure 5 report the dimension-level paired effects.

**Table 8. Paired effects on two-rater mean scores (0–2 per dimension; 0–8 total)**

| Comparison | Pairs | Company facts Δ | Regulatory evidence Δ | Citation support Δ | Uncertainty Δ | Total Δ |
|---|---:|---:|---:|---:|---:|---:|
| G2 − G1 | 41 | −0.009 | 0.237 | 0.000 | 0.000 | 0.228 |
| G3 − G2 | 38 | 0.000 | 0.000 | 0.013 | 0.000 | 0.013 |
| G3 − G1 | 42 | −0.009 | 0.285 | 0.013 | 0.000 | 0.289 |

**Figure 5.** Company-macro paired differences by dimension for the primary comparison. Intervals are pointwise 95% intervals from 20,000 company-clustered bootstrap replications; only observed pairs are included, and no multiple-comparison adjustment is applied.

### 5.4 Rater Differences and Scale Ceiling Effects

Across the 355 filtered provider answers, the two raters made 1,420 paired dimension-level judgments. Exact agreement was 86.20% for company facts, 57.75% for regulatory evidence, 97.46% for citation support, and 100.00% for uncertainty handling. The quadratic-weighted kappa for regulatory evidence was approximately 0.215. Rater 2’s regulatory scores were, on average, 0.417 points lower than Rater 1’s, indicating differences in scale use or judgment. The mean preserves information from both raters symmetrically but does not automatically turn their differences into consensus.

Citation-support exact agreement was 97.46%, with κ = 0. Uncertainty ratings were 2 for both raters on all 355 answers, so κ is not estimable because of the constant marginals. High agreement alongside near-perfect score distributions does not establish reliable claim-level semantic support. We do not treat either “the methods are identical” or “the scale lacks resolution” as a proven explanation. Table 9 and Figure 6 show rater distributions and ceiling diagnostics.

**Table 9. Rater-scale diagnostics**

| Dimension | Exact agreement | Weighted κ | Mean difference R2 − R1 | Rater 1 perfect-score rate | Rater 2 perfect-score rate |
|---|---:|---:|---:|---:|---:|
| Company facts | 86.2% | 0.400 | 0.115 | 81.4% | 93.0% |
| Regulatory evidence | 57.7% | 0.215 | −0.417 | 86.5% | 44.8% |
| Citation support | 97.5% | 0.000 | 0.025 | 97.5% | 100.0% |
| Uncertainty handling | 100.0% | Not estimable | 0.000 | 100.0% | 100.0% |

**Figure 6.** Score ceilings and rater perfect-score rates across 355 provider outputs. High agreement does not mean claim-level semantic support has been verified.

### 5.5 Complete-Case and Missingness Sensitivity

In the leave-one-company-out analysis, the G2–G1 difference ranged from [0.199, 0.241], and G3–G2 ranged from [0.000, 0.014]. The subset with outputs for all three primary conditions contained 33 questions from 18 companies; G2–G1 was +0.236 and G3–G2 was +0.014. Only 30 questions from 16 companies had outputs for all five retrieval methods; the corresponding differences were +0.203 and +0.016. Requiring all three questions for an entire company to be available reduced the subset to 12 questions from four companies, with G2–G1 at +0.125 and G3–G2 at 0. These are post hoc subsets selected by provider-output availability and cannot remove selection bias. In particular, 12 questions from four companies do not support cross-company generalization.

After excluding the session-generated responses, only 41 of 60 questions had paired G2–G1 scores. Using the observed score on one side where available and bounding missing scores between 0 and 8, the all-question mean-difference range was [−1.508, 1.292]; for G3–G2 it was [−1.567, 1.767]. Both ranges cross zero. The positive company-clustered interval among available pairs therefore cannot be generalized to a definite advantage across the full planned question set. These are algebraic missing-outcome bounds based on the scale endpoints, not confidence intervals. Table 10 and Figure 7 report leave-one-company-out ranges and the bounds.

**Table 10. Leave-one-company-out ranges and sharp bounds using observed one-sided scores**

| Comparison | Leave-one-company-out range | All-question sharp bounds | Wins / ties / losses |
|---|---:|---:|---:|
| G2 − G1 | [0.199, 0.241] | [−1.508, 1.292] | 13 / 28 / 0 |
| G3 − G2 | [0.000, 0.014] | [−1.567, 1.767] | 1 / 37 / 0 |
| G3 − no reranker | [−0.250, −0.196] | [−1.750, 0.517] | 2 / 23 / 20 |
| G3 − BM25 | [−0.260, −0.219] | [−1.792, 0.608] | 10 / 6 / 29 |

**Figure 7.** Missingness and leave-one-company-out sensitivity after excluding session-generated responses. The observed-effect interval is a pointwise 95% company-clustered bootstrap interval from 20,000 replications. The all-question algebraic bounds and the confidence interval are different estimands.

## 6 Retrieval Evidence and Case Analysis

### 6.1 Source Supply and Target-Location Coverage

Replay under the original configuration shows that G1 retained a mean of 8.183 annual-report passages and 1.183 regulatory passages, with both source types present in 68.3% of contexts. G2 retained five passages from each source and achieved 100% co-occurrence. Under the 6,000-token limit, the mean actual reference-token count was approximately 4,945 for G1 and 4,032 for G2, showing that a shared limit did not produce equal-length contexts. The observed competition primarily involved annual reports occupying more candidate slots; neither source was assumed in advance to dominate. Candidate-budget replay, fresh BM25 retrieval, and finer-grained location diagnostics are reported in Supplementary Materials S1–S2. These analyses explain operational boundaries and are not pooled with the primary answer ratings.

Source balance did not translate into better overall coverage of designated target locations. Mean annual-report page coverage was 79.67% for G1 and 74.33% for G2; regulatory-location coverage was 0% and 3.89%, respectively. The mean across both roles was 39.83% for G1 and 39.11% for G2. The number of questions with at least one matched reference page from each source type increased from 0 to 6 of 60. Because strict source hashes do not merge equivalent regulatory forms, these values do not mean that “only 3.89% of regulations were relevant,” nor do they represent exhaustive evidence recall. Table 11 and Figure 8 report source supply and strict target-location proxies.

**Table 11. Source supply and strict target-location proxies under the original configuration**

| Strategy | Mean A/R passages | Actual tokens | Both source types present | A-page coverage | R-location coverage | Macro coverage across roles |
|---|---:|---:|---:|---:|---:|---:|
| Dual route | 5.00 / 5.00 | 4,032 | 100.0% | 74.3% | 3.9% | 39.1% |
| Merged | 8.18 / 1.18 | 4,945 | 68.3% | 79.7% | 0.0% | 39.8% |

**Figure 8.** Replay of source allocation. Co-occurrence of both source types is a supply measure and does not substitute for reference-page coverage or semantic support.

### 6.2 Examples and Disagreements

Cases were selected post hoc based on observed score differences and are not randomly representative. One positive example is the iFLYTEK audit-committee question. Both raters increased the regulatory-evidence score from 1 to 2, with total scores of 7, 8, and 8 for G1, G2, and G3, respectively. The review notes indicate that G1 did not contain original regulatory text of type R. This case is consistent with the explanation that evidence supply may be insufficient, but it does not establish the causal mechanism for all questions.

As a post hoc example of a provider-generated answer, the Luxshare Precision audit-committee question received two-rater mean scores of 7.0, 8.0, and 8.0 for G1, G2, and G3, respectively. Based on the retrieved passages, G3 reported committee members, meeting counts, and some duty-performance activities; these passages did not identify member status or the convener. A review of the full 2024 annual report found that other sections listed Liu Zhonghua, Song Yuhong, and Hou Lingling as independent directors and Zhang Ying as a former independent director, recording Zhang’s departure on 18 May 2024. However, the audit-committee meeting table still listed Zhang among its four members for meetings on 23 August and 25 October 2024, creating an inconsistency in the report’s own membership timeline. The report did not identify the audit-committee convener [31]. Because the annual report itself contains this record conflict and the temporal applicability of the supplied regulatory versions was not verified, this case cannot support a compliance judgment. It illustrates that both retrieved-passage coverage and consistency within the source document affect verification. This single post hoc case does not explain the main effect.

G2 and G3 used character-for-character identical retrieved contexts and received the same score in this case. It shows that role prompting did not add points for this question, but it cannot establish that prompting is generally ineffective. The case and ratings came from provider outputs under the primary protocol; session-generated responses were excluded. Table 12 presents an excerpt from the output.

**Table 12. Post hoc example of a provider-generated answer**

| Question | Scores for G1/G2/G3 | G3 answer excerpt | G3 citation-ID excerpt |
|---|---:|---|---|
| 002475SZ-2024-AUDIT_COMMITTEE | 7.0 / 8.0 / 8.0 | *Annual-report disclosure (supported by the source):* (1) Committee composition: Luxshare Precision’s 2024 annual report states that the audit committee comprised Liu Zhonghua, Song Yuhong, Hou Lingling, and Zhang Ying (four members) and held four meetings during the reporting period [A1]. The report also states that the board had seven directors, including three independent directors (experts in law, accounting, and related fields); the board… **[translated excerpt; source excerpt ends here]** | A1 |

The accompanying case inventory retains the complete 120-character excerpts, dimension-level scores from both raters, source-response files and SHA-256 values, and review-note fields. The table excerpt is translated from the beginning of the actual `response.evaluation`; no omitted conclusion has been supplied. The citation-ID column lists only the IDs actually cited in that excerpt.

## 7 Discussion and Validity Limitations

### 7.1 Interpretation of the Positive Difference

The positive difference for dual-route retrieval relative to merged retrieval should be interpreted alongside the added source-supply analysis. If company material is reduced in the context, factual questions may lack company-specific details; if regulatory material is missing, normative comparisons may lack an explicit basis. However, the number of passages from each type is only a possible intermediate mechanism. Statistical association alone cannot establish that it causally mediated the total-score change. We do not treat candidate counts, page-location matches, and semantic support rates as interchangeable.

For systems operating on real documents, retaining source locations and actual contexts provides a traceability entry point for review and preserves records that help distinguish parsing, retrieval, context assembly, and generation errors. We checked consistency between records and replay but did not measure whether traceability improves review accuracy or reduces review costs. These engineering capabilities therefore do not offset negative answer-quality results; if a simpler configuration performs better, that result should be reported rather than selecting only comparisons that match expectations.

### 7.2 Why Prompt Constraints Should Not Be Assumed to Help

The absence of a stable increment from G3 over G2 first indicates that, under the present context and scale, adding source-role wording did not produce a discernible additional gain. G2’s shared prompt already required citations and constrained the evidence sources, and a capable generator may distinguish facts from normative requirements on its own. This is one possible explanation, not a cause independently tested here. Another possibility is that the rating scale is near its ceiling and cannot distinguish fine-grained differences in citation completeness.

We therefore do not recast a zero gain as “further proof that role prompting works,” nor do we interpret it as ineffective for every task. A more informative next study would define the required source role for each claim in advance, retain unknown and conflict categories, and measure on independent questions whether prompting changes the evidence actually used. It should not continue to expect a larger difference from an aggregate score already near its maximum.

### 7.3 Simple Baselines and Component Interpretation

Rerankers are commonly trained for relevance, but answer quality in this task also depends on company identity, disclosure details, regulatory topic, and material availability. A highly relevant passage may not contain all complementary information required for a complete assessment. Dense fusion may also add semantically similar material that does not support the specific matter at hand. These mechanisms can guide error analysis, but without passage-by-passage semantic review we cannot assert that a particular mechanism made the reranker harmful.

Rater differences in the direction of the BM25 comparison further show that mean results can conceal the effects of rating scale and dimension. Practical choices should consider effect size, cost, failure rate, and review difficulty rather than assuming that a more complex system is more advanced. We therefore retain BM25 and no-reranking as competitive comparisons and limit the conclusions to the implementations, questions, and rating scope used here.

### 7.4 Uncertainty in Professional Tasks

The score decline after removing one source type is consistent with evidence complementarity, but the ablation changes both evidence content and context length and cannot isolate a pure complementarity effect. A reasonable answer that acknowledges insufficient evidence may still score well on uncertainty handling. A cautious but incomplete answer can therefore retain a high total score. This is not necessarily a scale defect, because avoiding unsupported conclusions is important in professional QA. However, if answer completeness is also a target, completeness and conservatism must be measured separately.

Similarly, a high citation-support rating does not establish complete attribution for every rule. A passage on a page may support only part of a compound claim; a regulation may be semantically relevant but inapplicable because of its effective date or subject scope. We distinguish these layers to prevent professional-sounding system language from being mistaken for certification of a legal judgment.

### 7.5 Internal Validity

The primary comparison was not designed as a confirmatory experiment before any results had been observed. The original outputs had been viewed, and the simplified scale and mean-score summary were established at different stages; added diagnostics are post hoc and exploratory. Frozen hashes and historical records document the actual execution boundaries but cannot retrospectively remove prior exposure. We report pointwise intervals and do not present multiple exploratory comparisons as a family of confirmatory tests with controlled family-wise error.

Failed outputs are not assigned a quality score of zero, so differences among available outputs are conditional. Worst-case bounds show how unobserved quality could change the direction; leave-one-company-out analysis tests whether a single company cluster dominates. It does not resolve cross-company dependence caused by shared regulations. The two sensitivity analyses address different assumptions, and neither substitutes for additional observations.

### 7.6 External Validity and Resource Constraints

The company sample and report-year coverage are limited, and three topics do not represent the full range of listed-company self-regulatory evaluations. Shared regulations may create dependence across company clusters, while changes in disclosure templates and regulatory versions across years may also alter outcomes. The new budget replay uses existing candidates and does not discover evidence outside the candidate pool. It therefore measures packing sensitivity under saved rankings, not full-system performance after rerunning retrieval at arbitrary budgets.

The supplementary regulatory-version audit found that all questions concern 2024 reports, whereas the current knowledge base contains DOC100, the *Measures for the Administration of Information Disclosure by Listed Companies*, as Order No. 226 of 2025 (promulgated 26 March 2025; effective 1 July 2025); DOC128, the *Guidelines for the Articles of Association of Listed Companies*, as Announcement No. 6 of 2025 (promulgated and effective 28 March 2025); and DOC120, the *Code of Corporate Governance for Listed Companies*, as Announcement No. 18 of 2025 (promulgated 16 October 2025; effective 1 January 2026). The historical Order No. 182, the consolidated full text of the 2023 amendments to the Guidelines, and the 2018 Code of Corporate Governance were not independently added to the knowledge base; DOC343 is only the 2023 amendment decision [25–27].

Using the dates in the inventory, 64 of the 73 regulatory candidates in the frozen G1 merged top-10 results were dated after the report year, affecting 42 of 60 questions. For G2, 156 of 300 candidates were dated after the report year, affecting all 60 questions. The index’s `@DATE` convention is inconsistent: DOC100 records its adoption date (28 February 2025), DOC128 its promulgation date (28 March 2025), and DOC120 its effective date (1 January 2026) [25–27]. Thus, “dated after the report year” is only an index-time flag. Specific applicability requires checking the event date and the regulation’s promulgation, effective, amendment, and repeal status case by case. Retrieval and ratings involving these files reflect only the current corpus snapshot; they do not establish a hit rate against the historical regulatory versions applicable in 2024 or validate temporal compliance.

As of 27 October 2026, two submissions for regulatory-version review had passed structural checks, but 92 field discrepancies remained unresolved and no labels had been accepted. Reviewer identities had not been authenticated, and blinding had not been verified. These submissions were not used to update knowledge-base version metadata and do not provide independent evidence of temporal applicability.

The same-family K3 versus K2.8 service-alias comparison did not include a `reasoning_effort` parameter. Provider documentation lists default levels of `high` and `max`, respectively, but the responses do not record independently verifiable server-side levels, so reasoning budgets were not matched. The underlying checkpoint revisions were also not verified. The observed difference cannot therefore be attributed to model weights or described as cross-family generalization. One generation per unit is insufficient to estimate sampling variability. We use these limitations to constrain the conclusions, specifying which observations are supported and which require new independent experiments, rather than using them to avoid negative results.

### 7.7 Conclusions and Deployment Implications

For deployment, a simple configuration that preserves source identity, version, and location records may be preferred, with explicit distinctions among missing material, retrieval failure, and actual absence. For questions involving regulatory applicability, the interface should display available event-date and version evidence as well as unknown status. These recommendations follow from the observed source-supply and version limitations; this study did not directly test whether they reduce decision risk, review costs, or staff time.

We conducted a controlled comparison of dual-source retrieval configurations for question answering over listed-company annual reports and regulations. For the 41 questions with provider outputs for both G1 and G2, dual-route retrieval had a company-macro mean score 0.228 points higher on the 0–8 scale (pointwise 95% company-clustered interval [0.110, 0.355]). However, the all-60-question mean-difference bounds, retaining observed one-sided scores, were [−1.508, 1.292] and crossed zero. This is an observed difference among available pairs and does not establish a definite advantage over the full planned question set. With identical evidence, source-role prompting differed from dual-route retrieval by +0.013 points over 38 pairs ([0.000, 0.039]) and showed no stable increment. Source-removal conditions cover only 20 questions and alter evidence content and context length together; their available-case means cannot establish a pure source effect. Source co-occurrence and target-location coverage do not establish claim-level semantic support. The results are therefore limited to the present sample, model, and rating protocol and do not show that complex retrieval configurations generally outperform simpler baselines.

This study remains limited to 20 companies, 60 questions, one report year, an exploratory design, and a rating scale with ceiling effects. The regulatory knowledge base does not fully provide historical versions aligned with the 2024 reporting period, so the results do not validate historical regulatory applicability. Human ratings are not retrieval Precision or Recall, nor answer Accuracy. Stronger claims would require separate question sets, relevance judgments, and blinded review protocols.

## Data and Code Availability

Reproducible analysis scripts, aggregate results, replay details, raw chart data, and input-hash manifests are retained in the project materials. The public repository URL for the paper and the scope of source-file redistribution have not been determined; no public link is invented. Source files, ratings, and run records are retained, and any public release must follow the applicable licenses.

## References

[1] Lewis P, et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *Advances in Neural Information Processing Systems* 33 (NeurIPS 2020): 9459–9474. https://proceedings.neurips.cc/paper/2020/hash/6b493230-Abstract.html

[2] Chen Z, et al. FinQA: A Dataset of Numerical Reasoning over Financial Data. *EMNLP*, 2021: 3697–3711. https://doi.org/10.18653/v1/2021.emnlp-main.300

[3] Zhu F, et al. TAT-QA: A Question Answering Benchmark on a Hybrid of Tabular and Textual Content in Finance. *ACL-IJCNLP*, 2021: 3277–3287. https://doi.org/10.18653/v1/2021.acl-long.254

[4] Choe J, Kim J, Jung W. Hierarchical Retrieval with Evidence Curation for Open-Domain Financial Question Answering on Standardized Documents. *Findings of ACL*, 2025: 16663–16681. https://doi.org/10.18653/v1/2025.findings-acl.855

[5] Siddharth L, Luo J. Retrieval augmented generation using engineering design knowledge. *Knowledge-Based Systems* 303 (2024): 112410. https://doi.org/10.1016/j.knosys.2024.112410

[6] Yang W, Some L, Bain M, Kang B. A comprehensive survey on integrating large language models with knowledge-based methods. *Knowledge-Based Systems* 318 (2025): 113503. https://doi.org/10.1016/j.knosys.2025.113503

[7] Robertson S, Zaragoza H. The Probabilistic Relevance Framework: BM25 and Beyond. *Foundations and Trends in Information Retrieval* 3(4), 2009: 333–389. https://doi.org/10.1561/1500000019

[8] Karpukhin V, et al. Dense Passage Retrieval for Open-Domain Question Answering. *EMNLP*, 2020: 6769–6781. https://doi.org/10.18653/v1/2020.emnlp-main.550

[9] Zhang Y, et al. Qwen3 Embedding: Advancing Text Embedding and Reranking Through Foundation Models. arXiv, 2025. https://arxiv.org/abs/2506.05176

[10] Cormack G V, Clarke C L A, Buettcher S. Reciprocal rank fusion outperforms condorcet and individual rank learning methods. *SIGIR*, 2009: 758–759. https://doi.org/10.1145/1571941.1572114

[11] Alier M, García-Peñalvo F J, Casañ M J, Pereira J, Granados A. Closing the acronym gap in educational retrieval with ontology-guided augmentation. *Information Sciences* 740 (2026): 123181. https://doi.org/10.1016/j.ins.2026.123181

[12] Asai A, Wu Z, Wang Y, Sil A, Hajishirzi H. Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection. *ICLR*, 2024. https://arxiv.org/abs/2310.11511

[13] Yan S Q, Gu J C, Zhu Y, Ling Z H. Corrective Retrieval Augmented Generation. arXiv, 2024. https://arxiv.org/abs/2401.15884

[14] Jeong S, Baek J, Cho S, Hwang S J, Park J. Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models through Question Complexity. *NAACL*, 2024: 7036–7050. https://doi.org/10.18653/v1/2024.naacl-long.389

[15] Han W, Xiao X, Li Y, Wang J, Pechenizkiy M, Fang M. Adaptive iterative retrieval for enhanced retrieval-augmented generation. *Neurocomputing* 666 (2026): 132272. https://doi.org/10.1016/j.neucom.2025.132272

[16] Yao S, et al. ReAct: Synergizing Reasoning and Acting in Language Models. *International Conference on Learning Representations (ICLR 2023).* https://arxiv.org/abs/2210.03629

[17] Li B, Fan S, Zhu S, Wen L. CoLE: A collaborative legal expert prompting framework for large language models in law. *Knowledge-Based Systems* 311 (2025): 113052. https://doi.org/10.1016/j.knosys.2025.113052

[18] Wang H, et al. Learning to break: Knowledge-enhanced reasoning in multi-agent debate system. *Neurocomputing* 618 (2025): 129063. https://doi.org/10.1016/j.neucom.2024.129063

[19] Gao T, Yen H, Yu J, Chen D. Enabling Large Language Models to Generate Text with Citations. *EMNLP*, 2023: 6465–6488. https://doi.org/10.18653/v1/2023.emnlp-main.398

[20] Es S, James J, Espinosa Anke L, Schockaert S. RAGAs: Automated Evaluation of Retrieval Augmented Generation. *EACL System Demonstrations*, 2024: 150–158. https://doi.org/10.18653/v1/2024.eacl-demo.16

[21] Ru D, et al. RAGChecker: A Fine-grained Framework for Diagnosing Retrieval-Augmented Generation. *Advances in Neural Information Processing Systems* 37 (NeurIPS 2024), Datasets and Benchmarks Track. https://doi.org/10.52202/079017-0692

[22] Pipitone N, Alami G H. LegalBench-RAG: A Benchmark for Retrieval-Augmented Generation in the Legal Domain. arXiv, 2024. https://arxiv.org/abs/2408.10343

[23] Liu N F, et al. Lost in the Middle: How Language Models Use Long Contexts. *Transactions of the Association for Computational Linguistics* 12 (2024): 157–173. https://doi.org/10.1162/tacl_a_00638

[24] Kimi. Model configuration. Service-alias and default-reasoning-level information; underlying checkpoint revisions and runtime levels have not been verified. Accessed 20 and 23 October 2026. https://www.kimi.com/help/kimi-code/models

[25] China Securities Regulatory Commission. Order No. 182, *Measures for the Administration of Information Disclosure by Listed Companies* (2021), and Order No. 226, *Measures for the Administration of Information Disclosure by Listed Companies* (2025). https://www.csrc.gov.cn/csrc/c101864/c2ee1a791fddc4f5ebeeb70aa8e2399cf/content.shtml; https://www.csrc.gov.cn/csrc/c101953/c7547359/content.shtml

[26] China Securities Regulatory Commission. Announcement No. 62, *Decision on Amending the Guidelines for the Articles of Association of Listed Companies* (2023), and Announcement No. 6, *Guidelines for the Articles of Association of Listed Companies* (2025). https://www.csrc.gov.cn/csrc/c101954/c7449659/content.shtml; https://www.csrc.gov.cn/csrc/c101954/c7547791/content.shtml

[27] China Securities Regulatory Commission. Announcement No. 29, *Code of Corporate Governance for Listed Companies* (2018), and Announcement No. 18, *Code of Corporate Governance for Listed Companies* (2025). https://www.csrc.gov.cn/csrc/c101864/c1024585/content.shtml; https://www.csrc.gov.cn/csrc/c101954/c7589726/content.shtml

[28] Wang R, Balloccu S. ARQA: A Benchmark for Grounded Table–Text QA in Enterprise Annual Reports. *Proceedings of the 19th Conference of the European Chapter of the Association for Computational Linguistics, Industry Track*, 2026: 847–868. https://doi.org/10.18653/v1/2026.eacl-industry.63

[29] Zhu T, Liu M, Kurfali M. CFQA: A Chinese Financial Question Answering Benchmark from Corporate Annual Reports. *Proceedings of the 7th Financial Narrative Processing Workshop*, 2026: 28–38. https://doi.org/10.63317/4e6fhrncfrbu

[30] Cheng H, Wang K, Wang Q, Liu T, Sheng K. A Chinese financial event knowledge graph-based retrieval-augmented generation framework for financial question answering. *Engineering Applications of Artificial Intelligence* 175 (2026): 114670. https://doi.org/10.1016/j.engappai.2026.114670

[31] Luxshare Precision Industry Co., Ltd. *2024 Annual Report*. CNINFO, 26 April 2025. https://static.cninfo.com.cn/finalpage/2025-04-26/1223326862.PDF (accessed 28 October 2026).

## Appendix A. Replay and Audit Reproduction

The analysis-continuation freeze is recorded in `results/runs/paper_execution_freeze_windows_20261020_01/execution_freeze.json` (SHA-256 `f0eecd3e4f7f129364311b2daa86d0e2ca6aad6af57ac269a14c210be3ffc2c7`). It fixes existing references, company grouping, and primary settings and seals later recovery/extension decisions; it is not retrospective preregistration. The original execution plan is recorded separately in `results/runs/compact_final_execution_windows_20261020_01/execution_plan.json`. Both records point to the same reference-manifest SHA-256, `9f9c0f73fb0ae308394399dfd57f25d2deaca6ae5ad141b6acb5d425a9d91fc3`. The original primary results are not overwritten by added analyses. Added replay, sparse-retrieval, and rating diagnostics are retained in separate retrieval, quality, and audit subdirectories for this manuscript; scripts and input hashes are listed in the delivery manifest.

Execution checks cover 400 planned units, 355 provider outputs included in the analysis, 386 historical rating records and their 3,088 original rating fields; 31 session-generated responses were excluded from the reanalysis. All 120 contexts under the original configuration were reproduced character for character, and 123 reference-source locations could be found in the index. Raters are identified in the text as Rater 1 and Rater 2. Historical scores and failures are retained; added analyses are not retrospectively described as preregistered.

## Appendix B. Writing and Submission Status

This English working translation is based on the Chinese empirical manuscript, which compares retrieval organization for annual-report and regulatory RAG. Author names, affiliations, funding, conflicts of interest, CRediT roles, and disclosure of AI-assisted writing must be completed by the authors based on the facts. The single-column layout with editable tables is informed by full-text domain-RAG empirical papers; it does not reproduce a publisher masthead or imply publication status. After author information is verified and a target journal selected, the manuscript must still be formatted to that journal’s template. Length and figure count do not establish journal quartile or guarantee acceptance. Cross-year and agent extensions remain in the separate merged extension manuscript and are not part of this paper’s primary results.

