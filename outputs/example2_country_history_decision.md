# Deliberation Decision Document
**Feature Request:** Project managers should be able to see the full history of engagement with a country before starting a new mission.

**Termination Reason:** `CONVERGENCE_ALL_ISSUES_RESOLVED_OR_ESCALATED (CRITIC_SIGNALED_CONVERGENCE)` | **Final Disagreement Score:** `0.0` | **Confidence (Proposer / Critic):** `0.76` / `0.40`

## Executive Summary
v1 is a read-only Country Engagement History panel on the Country record and as a pre-flight step in the New Mission flow. It shows a reverse-chronological timeline built only from existing Engagement, Mission, Project and Contact records, with no new tables, no new fields and no coordinator work. The main trade-off argued was completeness and safety against a no-schema, no-RBAC MVP. Permission checks run inside the query, contact rows carry staleness and attribution labels, and a caveat says the view is not proof of no prior contact. Two questions need a human decision: whether PMs may see other teams' engagement history in a country (C1), and whether the banner may disclose that restricted active missions exist (C4).

## 1. Agreed Scope
### Included in Scope (v1 MVP)
- Read-only 'Country Engagement History' panel on the Country record, also shown as a pre-flight step in the 'New Mission' flow, built only from existing Engagement, Mission, Project and Contact records
- Single reverse-chronological timeline per country combining Engagements, past/active Missions and Project affiliations; each row shows date, type, summary, linked Contact, and linked Mission/Project
- Deterministic country attribution with fixed precedence (Engagement.country_id, then Mission's country, then Project's country, then Contact's country), deduplicated by record ID so multi-path links never double-count
- Display-only label on rows attributed through the Contact fallback: "Linked via contact's current country — may not reflect where this took place"
- Basic filters on existing fields only: date range, engagement type, linked Project/Mission
- Permission enforcement inside the database query, so rows, totals, page counts and the 'N engagements' summary come from the same permission-filtered set with no post-fetch filtering. Who can see what follows the existing Country/Mission access model unchanged (see open question C1)
- A row is shown only if the user can open its primary record (Engagement or Mission). Linked Contacts or Projects the user cannot open render as 'Restricted contact' or 'Restricted project', and rows are never shown partially
- Contact staleness marker computed from existing fields: 'Contact record changed since this engagement — role/person may differ', plus a 'Deactivated' tag where applicable
- 'Active missions' banner showing the active missions the user can view in full (the restricted-mission count line is pending human decision C4 and is not included until approved)
- Static caveat in the panel footer and empty state: 'Shows records linked to this country; unlinked or restricted records are not included. Records linked only through a contact appear under that contact's current country. Not a guarantee of no prior contact.'
- Keyset pagination on (date, id) over the permission-filtered set, 50 rows per page
- Non-blocking behavior: the New Mission flow shows the history link and visible-row summary but requires no acknowledgement
- Pre-release volume and permission-mix measurement on a production-sized copy, as a release gate task

### Explicitly Excluded from Scope
- Any new tables or entities (no 'EngagementSummary', 'Relationship' or historical role-graph tables)
- Backfill, cleanup or normalization of legacy engagement data
- Computed 'unlinked records' counts or data-quality dashboards (unreachable records cannot be attributed to a country)
- New data-entry fields or required manual steps for Regional Coordinators
- Historical point-in-time contact roles; snapshotting contact names or countries onto engagements
- Re-attributing contact-derived engagements to the country where they actually took place (needs stored location data or manual correction; v1 labels them instead)
- AI/ML summarization, sentiment or 'relationship health' scores, recommendations
- Mandatory acknowledgement/approval gate before creating a mission
- Custom RBAC, new classification/sensitivity tagging, or summary redaction workflows beyond existing access inheritance
- Cross-country or regional rollups
- Export, print or sharing outside the CRM
- Edit/annotate from the history view
- Integrations with external systems, notifications or alerts
- New admin or configuration screens for permissions, thresholds or banner behavior

### Success Criteria
- The first page (50 rows) loads in under 2 seconds at p95 for the largest country, measured on a production-sized copy with realistic restricted-row mix, before release
- 100% of ~100 countries render without errors, including an explicit empty state that carries the 'unlinked/restricted records not included' caveat
- Zero new database tables and zero new required fields for Regional Coordinators
- In UAT, at least 5 PMs find the most recent engagement and any active missions for a country in under 30 seconds unaided
- Permission test suite with 0 leaks across rows, linked Contact/Project names, summary text, row totals, page counts and the 'N engagements' summary, covering: Mission visible/Engagement hidden, Mission visible/Contact hidden, and PM with access to a single mission in the country
- Every page returns exactly 50 rows unless it is the last page, and the displayed total equals the count of rows the user can open (0 discrepancies in test data with 30%+ restricted rows)
- Test: a Contact modified or deactivated after an engagement date always shows the stale marker on that row, and a Contact unchanged since then never shows it (100% on fixture data)
- Test: an Engagement reachable by multiple link paths appears exactly once and under the precedence-determined country
- Test: every row attributed via the Contact fallback shows the 'contact's current country' label, and no row attributed via direct country, Mission or Project shows it (100% on fixture data, including a contact who moved from Country A to Country B)
- Test: the active-missions banner shows the restricted count line whenever a restricted active mission exists in the country, and never exposes its name, team or details
- Within 60 days of release, at least 60% of new missions are created by a PM who opened the history panel in the same session (from existing usage logs)

## 2. Surfaced Assumptions & Deliberation Outcomes
- **[A1] 'Full history' means all Engagement, Mission and Project-affiliation records already in the CRM that can be linked to the country, not external systems or undocumented interactions.** (Challenged: `False` -> Disposition: `ACCEPTED`)
  - *Notes:* No ledger issue targeted this assumption; it stood unchanged through all rounds.
- **[A2] Row visibility follows the existing record-level access model, applied as a query predicate, and a row is visible only if its primary record is openable. Whether a PM with access to one mission in a country should see other teams' country history is an access-policy decision needing human confirmation.** (Challenged: `True` -> Disposition: `ESCALATED_TO_HUMAN`)
  - *Notes:* C1: the Proposer revised the mechanics (in-query predicate, Restricted placeholders, aggregates), but the cross-team visibility policy question was escalated to a human by the Critic in R2 and stayed escalated.
- **[A3] The panel is an advisory orientation aid, not a compliance control. The banner is a best-effort signal and says explicitly when restricted active missions exist, subject to human sign-off on disclosing that count.** (Challenged: `True` -> Disposition: `ESCALATED_TO_HUMAN`)
  - *Notes:* C4: the Proposer revised the banner to add a count-only restricted-mission line. Whether to disclose that count was escalated to a human in R2 and stayed escalated.
- **[A4] Engagements can be attributed to a country through a fixed precedence of existing links (direct country, Mission, Project, Contact), deduplicated by record ID. Rows attributed only via the Contact fallback carry a visible label, and records with no reachable link are excluded with a static caveat.** (Challenged: `True` -> Disposition: `REVISED_AND_ACCEPTED`)
  - *Notes:* C3: the Proposer defended in R2, then in R3 revised to add the contact-fallback row label and extended caveat, and the Critic accepted. Residual risk of contact-derived engagements missing from the original country's timeline is covered by the caveat.
- **[A5] Per-country volume is hundreds to low thousands of rows and permission predicates can be pushed into the indexed query, verified on a production-sized copy before release.** (Challenged: `True` -> Disposition: `ACCEPTED`)
  - *Notes:* C5: the Proposer defended with in-query predicates, keyset pagination and a pre-release measurement gate, and the Critic accepted in R2.
- **[A6] Contacts show their current record data, with a deterministic stale marker when the Contact was modified or deactivated after the engagement date. Point-in-time role history is not tracked.** (Challenged: `True` -> Disposition: `REVISED_AND_ACCEPTED`)
  - *Notes:* C2: the Proposer revised to add the stale marker and 'Deactivated' tag using existing fields, and the Critic accepted in R2.

## 3. Open Questions Requiring Human / Policy Sign-Off
- [C1] Access-policy owner (e.g., Head of Diplomatic Security or Legal): Should a PM who has access to one mission in a country be able to see other teams' engagement history in that country under the existing Country/Mission access model, or must v1 restrict this further? The panel's row visibility depends on this answer; v1 currently ships with the existing model unchanged.
- [C4] Head of Diplomatic Security (diplomatic/security classification owner): May the 'Active missions' banner show a count-only line ('N more active missions exist that you cannot view — contact Country Operations') revealing that restricted active missions exist, with no names, teams or details? If yes, the line is added to scope; if no, the line is removed and only the footer caveat remains.
