# Deliberation Decision Document
**Feature Request:** The CRM should alert us when our relationship with a country goes cold.

**Termination Reason:** `DEADLOCK_ESCALATED_TO_HUMAN (C2)` | **Final Disagreement Score:** `0.0` | **Confidence (Proposer / Critic):** `0.80` / `0.40`

## Executive Summary
v1 derives a 'last meaningful engagement' date for each country from existing Engagement records and flags a country as cold after 90 days without one. Flagged countries appear on an in-app Cold Countries list that is filtered by the viewer's country scope and labelled 'Based on logged engagements only'. Countries with no active coordinator are marked 'Unassigned'. The main trade-off argued was alert noise and reliability against keeping v1 free of new tables, settings screens and manual dormant flags. The Proposer chose one derived stamp field and one global threshold with a backfill release gate. The Critic accepted the definition of 'meaningful', the unowned-country handling and the threshold gate. Two items need a human decision before the weekly email digest can be scoped: whether country names may appear in email at all (C1), and how never-engaged countries are handled in the digest (C2, where the agents deadlocked).

## 1. Agreed Scope
### Included in Scope (v1 MVP)
- Derive 'last meaningful engagement date' per Country from existing Engagement records, with no new data entry. Meaningful means type meeting, call or mission visit. Staff-logged email is excluded. Engagements with a null or future date are ignored. Engagements linked to more than 5 Countries are excluded as bulk entries (config constant). Merged or deleted Countries are skipped.
- Fixed system-wide 'cold' rule: no meaningful engagement with a Country in the last 90 days (a single config constant, no UI screen).
- Nightly batch job writing cold status, last meaningful engagement date and days-since as derived fields on Country. All reads go through the existing record-permission query layer.
- In-app 'Cold Countries' list view, sortable by days since last engagement. It shows Country, last engagement date, last contact (only if the viewer has existing Contact access and the contact is active in existing status data) and coordinator. Countries with no active coordinator show an 'Unassigned' label. The list is filtered by the viewer's existing Country scope and carries the static label 'Based on logged engagements only'.
- One-time pre-launch backfill dry run on historical engagements, run as a script with no UI. It reports the projected cold list size as a release gate, and the constant is adjusted before launch if the gate is exceeded.
- Alert visibility reuses the existing Country/Mission access model; no new permissions or roles. Job failures are reported through existing job-failure monitoring.

### Explicitly Excluded from Scope
- Per-country, per-tier or per-region thresholds and any settings UI (v1 uses one constant, tuned after the backfill and pilot data).
- Admin-set 'low-touch' or 'dormant' boolean, snooze, acknowledge, or any coordinator-facing manual workflow.
- New tables for alert state, relationship history, or historical role graphs. The one derived date field on Country is the only alert state.
- ML or weighted relationship-health scoring, sentiment analysis, or predicted churn.
- Automatic capture from email, calendar or phone systems.
- Escalation chains, approval workflows, or task assignment from alerts.
- Stale-contact detection beyond the existing contact status field, and role-change tracking for ministry contacts or project leads.
- Real-time, push, SMS or chat notifications.
- Building new job-monitoring infrastructure. The send job reuses existing failure alerting.
- Judging diplomatic sensitivity of why a relationship is quiet, and deciding whether country names may appear in email. Both are human policy and data-classification decisions.

### Success Criteria
- Nightly job completes for all ~100 Countries in under 10 minutes. The Cold Countries list matches an independent SQL check of the rule (including bulk, null-date and future-date exclusions) for 100% of 20 sampled countries in UAT.
- Zero new required fields or manual steps for Regional Coordinators in any existing form.
- Backfill gate before release: the projected cold list is at most 30% of countries, and projected newly-cold countries are at most 5 per coordinator per week on average. If either is exceeded, the constant is adjusted before launch.
- Digest reliability tests: (a) after a simulated skipped or failed weekly send, 100% of countries that went cold in that period appear in the next successful digest. (b) A country whose suppression lifts while still cold appears in the next digest. (c) No country appears in two digests within the same cold episode, across 100% of test cases. (d) A new meaningful engagement followed by a re-crossing triggers a fresh alert.
- Authorization test: a user scoped to country subset S sees zero Cold Countries rows or contact names outside S. The digest contains zero contact names. A user whose assignment is removed before send time receives no digest in 100% of test cases.
- Every Country with no active coordinator and newly cold appears in the Operations digest in 100% of test cases, and is labelled 'Unassigned' in the list.
- Pilot of 4 weeks: at least 50% of countries flagged newly cold receive a new meaningful Engagement within 30 days of first alert.
- Ships as derived fields on Country, one list view and one email job, with no new tables.

## 2. Surfaced Assumptions & Deliberation Outcomes
- **[A1] 'Cold' means no recent meaningful logged engagement, not a verdict on relationship quality. Meaningful excludes staff-logged email, bulk or mass entries (linked to more than 5 Countries), and null or future dates.** (Challenged: `True` -> Disposition: `REVISED_AND_ACCEPTED`)
  - *Notes:* C3 challenged clock-reset and bad-date risks. The Proposer revised the definition of meaningful and added the 'Based on logged engagements only' label, and the Critic accepted.
- **[A2] A single 90-day threshold is acceptable for v1, validated by a pre-launch backfill dry run before release.** (Challenged: `True` -> Disposition: `ACCEPTED`)
  - *Notes:* C5 asked for tiered thresholds and pre-launch validation. The Proposer defended the single threshold and added a numeric backfill release gate, and the Critic accepted.
- **[A3] The audience is Operations and Regional Coordinators, who need a weekly push of newly cold countries plus an always-available pull list. Countries without an active coordinator route to the existing Operations role.** (Challenged: `True` -> Disposition: `REVISED_AND_ACCEPTED`)
  - *Notes:* C4 raised unowned countries and departed owners. The Proposer added the Operations-role fallback and the 'Unassigned' label, and the Critic accepted.
- **[A4] The existing Country-to-Coordinator assignment and Country/Mission access model can be reused for the list query and the digest recipient check at send time. Email content is kept minimal because email leaves the CRM's access controls. Whether country names may appear in email at all is escalated to a human data-classification owner. If disallowed, the digest becomes a link-only notification.** (Challenged: `True` -> Disposition: `ESCALATED_TO_HUMAN`)
  - *Notes:* C1 engineering mitigations were accepted as adequate (scope-filtered list, no contact names in digest, send-time recipient check). The residual question of country names in email was escalated to humans in R2 and stayed escalated.
- **[A5] Some countries are legitimately quiet. The digest lists a country once per cold episode, tracked by one derived date field on Country (the last engagement date for which a digest was sent). Low-touch countries therefore appear in the push digest once per episode and then live only on the pull list.** (Challenged: `True` -> Disposition: `ESCALATED_TO_HUMAN`)
  - *Notes:* C2 went through three rounds and the Proposer revised to the stamp-field design. A null-date gap remained open and the gate escalated it as a deadlock (DEADLOCK_ESCALATED).

## 3. Open Questions Requiring Human / Policy Sign-Off
- [C1] Data-classification owner (with Legal / Information Security): may country names and 'gone cold' status appear in the weekly digest email at all? If yes, the digest carries country name and days-since only. If no, the digest becomes a link-only notification to the in-app list. The weekly digest (content, recipients and Operations fallback) is not in agreed scope until this is decided.
- [C2] Product Manager together with the Operations lead: the agents could not agree on how the once-per-episode digest handles countries with no qualifying engagement (null last-engagement date). Proposer position: a derived digest_stamped_for_date field on Country makes alerts once per cold episode and robust to failed sends and suppression lifts, and no admin low-touch boolean or snooze is needed in v1 (the Proposer did not respond to the null-date case before the deadlock). Critic position: the design is an improvement, but never-engaged countries have a null stamp and would be listed in every weekly digest forever, so either a fixed sentinel stamp (digest once, then stamp) or exclusion of never-engaged countries from the push digest (pull list only) is needed, with a test case. Decision needed: which of those two approaches, if either, should apply, and is the stamp-field design acceptable as the basis for the digest? The digest, its suppression rule and the launch-time stamping are not in agreed scope until this is decided.
