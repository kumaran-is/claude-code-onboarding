---
name: app-store-optimization
description: "App Store / Google Play listing optimisation (ASO): keyword research, metadata, competitor and review analysis, A/B test planning, ASO score, launch checklist. Use before a store release or when the user says ASO, store listing or app keywords. Not for uploading builds (asc-release-flow, gpd-release-flow)."
allowed-tools: Bash, Read, Write
metadata:
  triggers: ASO, app store optimization, keyword research, app store listing, metadata optimize, competitor analysis, app store keywords, ASO score, review sentiment, localization strategy, store listing, A/B test icon, launch checklist ASO, app description, app title optimize
  related-skills: asc-submission-health, asc-release-flow, gpd-submission-health, gpd-release-flow, changelog-generator, mobile-design
  domain: mobile-deployment
  role: specialist
  scope: optimization
  output-format: document
last-reviewed: "2026-03-15"
---

# App Store Optimization (ASO)

## Iron Law

**NO STORE SUBMISSION WITHOUT COMPLETING ASO HEALTH CHECK FIRST — TARGET SCORE ≥ 70/100**

Run `aso_scorer.py` before any first App Store or Play Store submission. A low score wastes review queue time and launch momentum.

## When to Use

- Before **first** App Store or Play Store submission
- Before each **major update** (new features, new screenshots, new markets)
- When **ratings drop** — use `review_analyzer.py` to find root causes
- When **downloads plateau** — keyword and competitor audit needed
- Before **expanding to new markets** — localization ROI assessment

## Platform Character Limits (enforced by `metadata_optimizer.py`)

| Field | Apple App Store | Google Play |
|-------|----------------|-------------|
| Title | 30 chars | 50 chars |
| Subtitle / Short description | 30 chars (subtitle) | 80 chars |
| Promotional text | 170 chars (editable without update) | — |
| Full description | 4,000 chars | 4,000 chars |
| Keyword field | 100 chars (comma-separated, no spaces, no plurals, no duplicates) | — (extracted from title + description) |
| What's New | 4,000 chars | — |

## Workflow

### Step 1 — Keyword Research
```
Use keyword_analyzer.py to:
- Score candidate keywords by volume/competition/relevance
- Find long-tail opportunities (3–4 word phrases, lower competition)
- Identify which competitor keywords have gaps
```
**Output**: Ranked keyword list — primary (title/subtitle), secondary (keyword field), long-tail (description)

### Step 2 — Metadata Optimization
```
Use metadata_optimizer.py to:
- Generate platform-specific title within character limit
- Write subtitle (Apple) / short description (Google)
- Craft conversion-focused full description
- Maximize Apple keyword field (100 chars, no wasted characters)
- Validate all character limits before writing
```
**Apple keyword field rules**: No spaces after commas, no plurals if singular exists, no words already in title, no competitor names.

### Step 3 — Competitor Analysis
```
Use competitor_analyzer.py to:
- Extract top 10 competitor keyword strategies
- Identify visual asset approaches (icon style, screenshot structure)
- Find keyword gaps — terms they rank for that you don't target
- Spot positioning opportunities
```

### Step 4 — ASO Health Score
```
Use aso_scorer.py to:
- Score 0–100 across 4 dimensions:
    Metadata Quality       (0–25): title, description, keyword density
    Ratings & Reviews      (0–25): average rating, volume
    Keyword Performance    (0–25): rankings in top 10/50/100
    Conversion Metrics     (0–25): impression-to-install rate
- Generate prioritized action list
```
**Gate**: Score ≥ 70 before proceeding to submission.

### Step 5 — A/B Test Plan (icon + screenshots)
```
Use ab_test_planner.py to:
- Design test hypothesis and variants
- Calculate required impressions for statistical significance
- Define success metric (impression-to-install rate target)
- Recommend test duration
```

### Step 6 — Review Sentiment Analysis (post-launch or before update)
```
Use review_analyzer.py to:
- Analyze sentiment distribution (positive/negative/neutral)
- Extract top complaint themes — rank by frequency
- Identify feature requests
- Generate response templates per complaint category
- Track sentiment trends across versions
```

### Step 7 — Localization (international expansion)
```
Use localization_helper.py to:
- Identify high-ROI markets by tier:
    Tier 1: en-US, zh-CN, ja-JP, ko-KR, de-DE, fr-FR
    Tier 2: es-ES, pt-BR, ru-RU, it-IT
    Tier 3: nl-NL, pl-PL, tr-TR, sv-SE
- Adapt keywords per locale (not direct translation)
- Validate character limits per language (German ≈ 1.3× English length)
- Estimate localization ROI before investing
```

### Step 8 — Launch Checklist
```
Use launch_checklist.py to:
- Generate platform-specific pre-launch checklist
- Validate Apple App Store compliance (metadata, screenshots, legal)
- Validate Google Play compliance (target API, content rating, privacy policy)
- Create update cadence plan
- Identify seasonal campaign opportunities
```

## Scripts Reference

| Script | Purpose | Key function |
|--------|---------|-------------|
| `keyword_analyzer.py` | Keyword scoring and research | `analyze_keyword()`, `find_long_tail()` |
| `metadata_optimizer.py` | Title/description/keyword field | `optimize_title()`, `optimize_keyword_field()` |
| `competitor_analyzer.py` | Competitor keyword + asset analysis | `get_top_competitors()`, `identify_gaps()` |
| `aso_scorer.py` | 0–100 ASO health score | `calculate_overall_score()`, `generate_recommendations()` |
| `ab_test_planner.py` | A/B test design + significance | `design_test()`, `calculate_sample_size()` |
| `localization_helper.py` | Multi-market localization | `identify_target_markets()`, `calculate_localization_roi()` |
| `review_analyzer.py` | Sentiment + theme extraction | `analyze_sentiment()`, `extract_common_themes()` |
| `launch_checklist.py` | Pre-submission checklist | `generate_prelaunch_checklist()`, `validate_app_store_compliance()` |

## Integration with Release Workflows

This skill runs **before** the technical submission skills:

```
app-store-optimization (Phase 0)
        ↓
asc-* skills (iOS: signing → TestFlight → submission → monitoring)
gpd-* skills (Android: upload → beta → health check → staged rollout)
```

`asc-submission-health` checks **technical** compliance (build state, encryption, screenshots exist).
This skill checks **content** quality (keyword strategy, conversion copy, ASO score).
They are different layers — both are required before a production submission.

## Anti-Patterns

- **Don't skip the ASO health check before submission.** Running `aso_scorer.py` after submission wastes review queue time — the gate is pre-submission.
- **Don't use the same keywords in both the title and the Apple keyword field.** Duplicate keywords waste the 100-character limit; keywords in the title already get indexed.
- **Don't directly translate metadata between locales.** Keyword intent differs by market — use `localization_helper.py` for locale-specific keyword research, not machine translation.
- **Don't run A/B tests without confirming statistical significance first.** Use `ab_test_planner.py` to calculate required impressions before declaring a winner.

## Verify

After running `aso_scorer.py`, confirm:
- Score output shows ≥ 70/100 before proceeding to submission.
- All character limits validated: `metadata_optimizer.py` must exit without limit warnings.
- Apple keyword field: run `grep "," <keyword_field>` to confirm no spaces after commas and no duplicates with the title.

## Limitations

- Keyword volume estimates are heuristic — no live Apple/Google API access
- Competitor data covers public store listings only
- A/B testing requires sufficient traffic for statistical significance (12,000+ impressions per variant)
- Store algorithms are proprietary and change without announcement

## Documentation Sources

| Source | How to Access | Purpose |
|--------|--------------|---------|
| Apple App Store guidelines | `WebFetch` apple.com/app-store/review/guidelines | Current metadata requirements |
| Google Play policy | `WebFetch` play.google.com/console/about/guides | Current Play Store requirements |
| ASO scripts | Read scripts in this skill directory | Run analysis functions |
