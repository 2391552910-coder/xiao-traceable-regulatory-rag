# Scoring-method claim audit: current candidate paragraph 78

Candidate: `年报与法规双源RAG_统一主文_引言检索表述收窄候选稿_待终审.docx`  
SHA-256: `76bca23f53ffac54da086f908397cae56b94586e43c6cc142734c10d12fedf0a`

## Checks

- The manuscript's four dimensions and allowed values (0/1/2/U) match the original rubric `compact-answer-rubric-0to8-v1`; the source-file SHA-256 is recorded below.
- The rubric specifies a 0–8 sum only when all four dimensions are numeric for both reviewers. Recalculation over the filtered score file found 355 outputs, 710 reviewer records, no U or invalid dimension values, and all 710 reviewer totals equal the sum of their four dimension scores.
- The manuscript says the rubric was defined after examining output availability and some answers and therefore treats these analyses as exploratory. That timing matches the rubric metadata and its revision receipt; the scoring scale was not preregistered.
- The score file contains 355 scored supplier outputs, matching the current manuscript's count; the 147/180 primary-run statement and exclusions remain bounded as described in the reanalysis record.

The wording in paragraph 78 is supported; no text change is indicated.

## Bound sources

- Rubric: `results/runs/paper_actual_output_review_windows_20261020_03/当前唯一使用包/scoring_rubric.json`, SHA-256 `02733eea59db7c3bf0b4b39a2910dd2650623d265255cce5e4ba693f92043b69`.
- Filtered scores: `results/runs/primary_generation_only_reanalysis_windows_20261028_01/per_output_scores_primary_model_only.json`, SHA-256 `374adf66ef594f318ff1720b6ee921640e0bcd6147006091e13dd6e4b390f124`.
- Filtered reanalysis: `results/runs/primary_generation_only_reanalysis_windows_20261028_01/analysis.json`, SHA-256 `09bc36867b146f6cb3849a1d52225c1c8054fc140a4d84481017e6609a371910`.
- Rubric revision and render record: `scoring_rubric_revision_receipt_20261028.json`.

## Limits

This verifies scale fidelity and arithmetic, not the semantic correctness of 355 answers, independence or identity of the two reviewers, or whether the exploratory scale is a validated measurement instrument. The high ceiling and absence of U do not establish high answer accuracy.

