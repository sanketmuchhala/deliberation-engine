# Deliberation Decision Document
**Feature Request:** We need a better way to track who is the right person to contact in each country.

**Termination Reason:** `CONVERGENCE_ALL_ISSUES_RESOLVED_OR_ESCALATED (CRITIC_SIGNALED_CONVERGENCE)` | **Final Disagreement Score:** `0.0` | **Confidence (Proposer / Critic):** `0.76` / `0.30`

## Executive Summary
v1 adds a derived, activity-based 'Suggested Contacts' panel on the Country record. It shows up to 3 contacts ranked by a fixed, documented rule over existing Contact, Mission, Project and Engagement data. It also supports a 'who do I contact in [Country] for [Project/Mission]' query from the Country page and global search. Permission filtering is applied before ranking, so hidden records cannot affect order, pins or counts. The main trade-off argued was zero-friction, deterministic ranking from existing data versus the risk of surfacing departed, junior, or otherwise wrong contacts. This was bounded with optional valid_to/inactive exclusions, a fixed caveat, and a passive 12-month label, but seniority and protocol ranking were deliberately left out. A human policy owner must still decide whether activity-ranked suggestions may be used for sensitive correspondence (C3).

## 1. Agreed Scope
### Included in Scope (v1 MVP)
- Derived 'Suggested Contacts (activity-based)' panel on the Country record showing up to 3 contacts, with a 'Show all N contacts' link to the existing permission-filtered contact list
- Fixed, documented ranking rule evaluated only over the user-visible set: (1) exclude contacts flagged inactive or whose Contact-Country link has a past valid_to; (2) rank contacts linked to an Active Mission or Open Project ahead of the rest, counting only records the user can read; (3) most recent readable Engagement date, with contacts with no visible engagement ranked last; (4) tie-break on primary_for_country, then alphabetical by name
- Optional valid_from / valid_to date fields on the existing Contact-Country link (no new table, no new screen); a past valid_to or the existing inactive flag removes the contact from ranking
- Each suggestion shows role/title, ministry, preferred channel, last engagement date (or 'no engagement recorded'), and a 'why shown' line, plus the fixed caveat 'Based on recorded activity, not verified current role or seniority. Confirm before sensitive correspondence.'
- Optional boolean 'primary_for_country' on the existing Contact-Country link that pins a contact to the top among contacts the user can see; it does not override inactive or expired valid_to
- 'last_verified' dropped and replaced by a read-only derived 'last engagement date' (visible engagements only), labelled as activity and not verification; a passive 'No engagement in 12+ months' label appears only on top-3 contacts, with no badge on list views
- Topic filter by Mission/Project via existing links only, applied only over Missions/Projects the user can read
- 'Who do I contact in [Country] for [Project/Mission]' from the Country page and global search, run live against the same permission-filtered query layer with no separate search index
- Server-side permission enforcement applied BEFORE ranking: candidate set, status boost, engagement recency, primary pin, 'no engagement' placement and the count N are computed only from records the user can read; 'why shown' falls back to 'Linked to this country' for unreadable records
- Confidential Missions/Engagements are defined by the existing access rules; v1 implements those and defines no new ones

### Explicitly Excluded from Scope
- No new Contact, Role, or Relationship tables and no multi-table historical role graph
- No verification workflow, 'confirm still current' task, approval chain, or follow-up ownership model in v1
- No ML or tunable scoring model; no UI config screens for ranking rules or thresholds
- No seniority, decision-maker, or protocol ranking (a diplomatic policy decision for humans, escalated under C3)
- No custom RBAC, new permission model, sensitivity tiers, or field-level classification; existing Country/Mission access only
- No bulk cleanup, dedup, or import of existing contact data; v1 uses data as it exists
- No separate search index for contacts or derived justification text
- No precomputed or cached global ranking shared across users; ranking is computed per request under the requesting user's permissions
- No automated outreach, email/calendar integration, or external directory sync for detecting turnover
- No cross-country or regional rollups

### Success Criteria
- Panel renders on 100% of Country records with at least one linked non-excluded Contact, with p95 load time under 2 seconds including per-request permission filtering
- Permission test suite in UAT explicitly covers the panel, the 'who do I contact' query, global search results, 'why shown' strings, and the 'Show all N' count; using at least 5 test users with differing Country/Mission access (including a user who sees Country X but not a confidential Mission Y), there are 0 cases of a contact, Mission/Project name, Engagement date, or count shown that the user cannot access directly
- Differential leakage test (automated): for a restricted user, adding, removing, or changing a Mission, Project, or Engagement they cannot read produces byte-identical panel order, pin placement, 'no engagement' placement, N, and 'why shown' text in 100% of test cases
- Contacts flagged inactive or with a past valid_to appear in 0 panel or query results (automated test)
- Pilot validation: for 20 sampled countries across at least 5 regions, the owning Regional Coordinator reviews the top-3 list once (one-off pilot measurement, not a product workflow), and at least 70% of lists contain the correct current primary contact; results reported with failure reasons (departed, junior-only, missing data) to inform v2
- Median time to find a contact for a given Country+Mission drops by at least 50% against a baseline measured pre-release on 10 timed tasks
- 0 new required fields for Regional Coordinators; the only new fields are optional (valid_from, valid_to, primary_for_country)
- 100% of displayed suggestions show the activity-based caveat, a last-engagement date or 'no engagement recorded', and a 'why shown' line; ranking output is deterministic (same data and same user permissions give the same order in repeated runs, 100% of test cases including ties and no-engagement contacts)
- The 'No engagement in 12+ months' label appears on no more than 30% of top-3 suggestions in pilot data; a higher rate triggers a v2 review of the label

## 2. Surfaced Assumptions & Deliberation Outcomes
- **[A1] 'Right person' means the best current point of contact for a country, optionally scoped by Mission or Project, not a single universal contact per country.** (Challenged: `False` -> Disposition: `ACCEPTED`)
  - *Notes:* No ledger issue targeted this assumption; it stood unchanged through all rounds.
- **[A2] Existing links and Engagement history are good enough to derive a useful suggestion. Departed contacts are excluded via the existing inactive flag or the new optional valid_to on the existing link, not via cleanup or detection.** (Challenged: `True` -> Disposition: `REVISED_AND_ACCEPTED`)
  - *Notes:* C1 challenged this in R1; the Proposer revised it in R2 (dropped last_verified, added optional valid_to, added caveat) and the Critic accepted, noting residual risk from unrecorded departures is acceptable for an MVP.
- **[A3] Recency of engagement and active Mission/Project linkage are acceptable proxies for 'who is currently being dealt with' in v1, and the panel is decision support, not an authoritative routing engine.** (Challenged: `True` -> Disposition: `ESCALATED_TO_HUMAN`)
  - *Notes:* C3 was defended by the Proposer in R2 (caveat, tie-break and no-engagement rules, 'Show all N', pin, coordinator-validated pilot) and escalated by the Critic because seniority/protocol precedence is a policy decision; it stayed escalated.
- **[A4] Users are Operations and Country Engagement staff. The panel, query, and justification text are computed server-side per request, with the existing Country/Mission/Engagement record-level permission filter applied to the candidate set and to every ranking input (status boost, recency, pin, count), and no separate index.** (Challenged: `True` -> Disposition: `REVISED_AND_ACCEPTED`)
  - *Notes:* C2 was revised in R2 and again in R3 (permission filtering before ranking, differential leakage test); the Critic accepted in R3.
- **[A5] Position changes are not detected automatically in v1. Turnover is handled by an optional valid_to or the inactive flag, and by a passive 'No engagement in 12+ months' label on top-3 contacts only.** (Challenged: `True` -> Disposition: `ACCEPTED`)
  - *Notes:* C4 was defended by the Proposer in R2 and accepted by the Critic as adequate for an MVP, given the passive label, top-3-only display, and the 30% pilot threshold.
- **[A6] Whether a person is appropriate for a sensitive topic, and seniority or protocol precedence, are diplomatic/policy judgments outside the CRM's remit and are escalated to a human policy owner.** (Challenged: `False` -> Disposition: `ACCEPTED`)
  - *Notes:* No ledger issue targeted this assumption directly; it was revised in R3 to reference the escalation, which relates to C3 under A3.

## 3. Open Questions Requiring Human / Policy Sign-Off
- [C3] Policy owner for diplomatic protocol (e.g., Head of Diplomatic Security or Regional Director, with Legal as needed): may the activity-ranked 'Suggested Contacts' panel, which ranks by engagement recency and Mission/Project linkage and not by seniority or protocol precedence, be used for sensitive or urgent correspondence as-is with its caveat, and should any seniority/protocol precedence rule be defined for a later version? Until decided, v1 treats the panel as decision support only and includes no seniority ranking.
