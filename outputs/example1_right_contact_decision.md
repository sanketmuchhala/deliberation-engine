# Deliberation Decision Document
**Feature Request:** We need a better way to track who is the right person to contact in each country.

**Termination Reason:** `CONVERGENCE_ALL_ISSUES_RESOLVED_OR_ESCALATED (CRITIC_SIGNALED_CONVERGENCE)` | **Final Disagreement Score:** `0.0` | **Confidence (Proposer / Critic):** `0.70` / `0.35`

## Executive Summary
v1 adds a 'Who to contact' panel on the country page. It shows one suggested first contact and up to two alternates, ranked by fixed, reproducible rules over existing Contact, Mission, Project and Engagement data. Each suggestion shows its ranking basis and a country-level disclaimer. The panel runs under the viewer's own permissions. The main trade-off was how far to trust engagement and role data for a diplomatic audience. It was settled by removing the 180-day stale badge and mission-based default ranking, by using role priority only where roles come from a controlled list, and by adding a pre-launch data-quality audit gate. It also leaves out new fields, tables, and verification workflows. All four challenged issues (C1-C4) ended ACCEPTED, no scope is pending, and no questions are escalated to humans. The pilot accuracy threshold and the audit gate's numeric cutoff still need to be fixed before launch.

## 1. Agreed Scope
### Included in Scope (v1 MVP)
- Country page 'Who to contact' panel: 1 suggested first contact plus up to 2 alternates. Each shows its details, the contact's role exactly as recorded, the last-engaged date, and a one-line ranking basis. A fixed header reads 'Country-level default, not topic-specific. Select a mission or project to narrow.' Reasons are built only from records the viewer can see.
- Deterministic ranking over existing Country, Contact, Mission, Project and Engagement data. Order: (1) linked to the mission or project the user selected; this step is skipped at country level, so the default view never ranks by whichever mission is most active; (2) role priority, applied only to role values in an existing controlled list, with free-text or blank roles skipped at this step; (3) most recent engagement; (4) has a contact method on file. Ties break on most recent engagement, then alphabetically.
- Optional context selector listing only the active Missions and Projects for that country that the viewer is already permitted to see. It uses existing records and has no new topic taxonomy.
- Neutral last-engaged date with a fixed label 'Engagement date does not confirm the person still holds this role'. The 180-day 'possibly stale' badge is removed because it is noisy and could be misread as validation.
- Exclude from recommendations, and show as 'marked inactive', any contact already flagged inactive or ended on the existing Contact record. This is a rule over existing data. If no such field exists, it is a no-op and no field is added.
- Computed 'no contact method on file' indicator for contacts lacking email and phone, shown inline in the panel only. The wording says 'on file', not 'valid'.
- Fallback: if no contact qualifies, show 'No recommended contact' and the country's full existing contact list, rather than guessing.
- Panel queries run under the viewing user's existing Country/Mission/Contact/Engagement permissions, not service-level access. Any reason clause, alternate, or selector entry that depends on a record the viewer cannot see is omitted. No new permission types are added.
- Pre-launch read-only data-quality audit query (not a user feature) reporting the share of contacts with a controlled role, with a contact method, and with at least one engagement, per country. It is a release gate: if role coverage is too low in a country, the role-priority step is not trusted there and the panel falls back to the full list.

### Pending Human Decision (relies on an escalated issue)
- None.

### Explicitly Excluded from Scope
- Manual 'primary contact' designation fields or any new data-entry step for Regional Coordinators
- New tables or entities (e.g. a ContactRole, Topic, Preference or role-mapping table); v1 uses computed queries over existing entities
- ML or scoring models; ranking is fixed, explainable rules
- Contact verification or confirmation workflows, 'last confirmed' fields, approval steps, or review queues
- Role-ended or turnover tracking beyond any inactive flag that already exists
- Notifications, alerts, or dashboards for stale contacts, and any staleness badge based on a fixed day threshold
- Per-country configuration or settings for ranking rules or thresholds
- Role normalization, translation or mapping tooling, and deduplication or contact-method validation (bounce or number checks)
- Availability, out-of-office, time-zone, or language-preference handling
- External directory sync or bulk import
- Protocol, precedence, or seniority rules between officials, and security clearance or data classification handling; these are policy decisions for humans, not product design
- Cross-country search or 'who handles topic X across all countries' views

### Success Criteria
- Coverage, not correctness: at launch, on existing data, at least 90% of the ~100 countries show a suggested contact with a contact method on file (measured by a query).
- Correctness: in a 10-country pilot review of 50 sampled lookups, at least 90% of suggested contacts are judged correct or acceptable by the responsible Regional Coordinator. Every miss is root-caused (departure, role data, access, ranking), and zero sampled lookups may suggest a contact the coordinator knows has left the role.
- Access: an automated test with a user who has Country access but no Mission access passes 100%. It confirms the panel shows no mission names, mission-derived reason text, mission-based ranking, or selector entries the user cannot see.
- Pre-launch data-quality audit is run and published for all countries before release, and the role-priority step is disabled or the list fallback is used wherever role coverage is below the audit gate.
- Zero new required fields or data-entry steps for Regional Coordinators, and zero new database tables in v1.
- The panel loads in under 2 seconds at p95, and a user reaches a suggested contact within 2 clicks from the country page.
- Every suggestion displays its ranking basis and the country-level disclaimer, and 100% of rankings are reproducible: identical data and permissions yield identical output.
- The v1 feature ships within a single release cycle.

## 2. Surfaced Assumptions & Deliberation Outcomes
- **[A1] 'Right person' means the best current contact for a given country, optionally narrowed to a mission or project; it is not a global directory or a per-topic expertise map.** (Challenged: `True` -> Disposition: `REVISED_AND_ACCEPTED`)
  - *Notes:* Challenged in C4 (a single authoritative answer could send a coordinator to the wrong person for a topic). The Proposer revised it by dropping mission-based ranking from the country default and adding a fixed disclaimer, and the Critic accepted.
- **[A2] The existing Contact role, contact-detail and Engagement data is complete enough to rank contacts with simple deterministic rules, without any new fields being filled in.** (Challenged: `True` -> Disposition: `REVISED_AND_ACCEPTED`)
  - *Notes:* Challenged in C3 (role and contact data quality). The Proposer revised it with controlled-list-only role priority, 'on file' wording, a pre-launch audit gate and separate coverage and correctness criteria, and the Critic accepted.
- **[A3] Engagement history shows when we last interacted with a contact but cannot confirm they still hold the role; v1 shows that date neutrally and relies only on any inactive status already on the Contact record.** (Challenged: `True` -> Disposition: `REVISED_AND_ACCEPTED`)
  - *Notes:* Challenged in C1 (recency cannot detect departure). It was reworded so the last-engaged date is shown neutrally and only an existing inactive flag is used, with the stale badge removed, and the Critic accepted.
- **[A4] Existing Country/Mission access controls already determine who may see which contacts, so the new panel needs no separate permission model.** (Challenged: `True` -> Disposition: `REVISED_AND_ACCEPTED`)
  - *Notes:* Challenged in C2 (leaks through derived reasons and the selector). It was kept as worded and honoured by running queries under the viewer's permissions and omitting anything depending on records the viewer cannot see, and the Critic accepted.
- **[A5] Mission and Project affiliation, as already recorded on contacts, is the only context needed to tailor the recommendation in v1.** (Challenged: `False` -> Disposition: `ACCEPTED`)
  - *Notes:* Not challenged in the deliberation; accepted as proposed.

## 3. Open Questions Requiring Human / Policy Sign-Off
- None. No issue was escalated to humans.

## 4. Issue Ledger (computed by the engine)
| Issue | Assumption | Proposer moves | Rounds challenged | Final state | Challenge |
|---|---|---|---|---|---|
| C1 | A3 | REVISED | 1 | `ACCEPTED` | Staleness is inferred from engagement recency, but turnover (minister reshuffle, ministry staff departure, our coordinator leaving) is not the same as silence. A contact who left office yesterday but was engaged 12 days ago is ranked first with a 'Lead on active mission; last engaged 12 days ago' reason and no stale badge, so a coordinator confidently calls or emails a departed official or sends sensitive material to the wrong ministry person. Conversely, a correct contact in a low-frequency relationship (say, a country with 1-2 engagements a year) gets flagged 'possibly stale' after 180 days. Across 100 countries most contacts get the badge, and people learn to ignore it. Recency also rewards whoever was logged most often, not who currently holds the role. The proposal has no signal for 'role ended' or 'recently confirmed', and the UI presents the result as authoritative. |
| C2 | A4 | REVISED | 1 | `ACCEPTED` | The panel claims to inherit the existing Country/Mission access model, but it does something new: it ranks and generates reasons from Engagement history, mission links and last-engaged dates. A user with Country access but not Mission access could infer the existence of a confidential mission, or see a reason string like 'Lead on active mission X; last engaged 12 days ago', when engagement notes or mission membership are restricted. The context selector lists Missions and Projects per country, and may reveal missions the user is not on. Ranking over contacts they can see can still disclose hidden data through the derived 'reason' text, the alternates, or the fact that a restricted contact is skipped. It is also unverified that existing access is actually enforced at contact, engagement and mission level, rather than at country level only. Least privilege may be broken at the aggregation layer, not at the row layer. |
| C3 | A2 | REVISED | 1 | `ACCEPTED` | The claim that existing Contact role, detail and Engagement data is 'complete enough' is unvalidated. Role is likely free text or an inconsistent field across 100 countries (e.g. 'Minister', 'Ministre', 'Focal Point', blank). 'Role priority from the existing role field' then ranks arbitrarily or misorders, such as a junior desk officer ahead of the Director. Duplicate contacts, or contacts never logged in Engagement, are ranked low or never. 'Has a valid contact method' is only presence, not validity, so a bounced email or disconnected number counts as valid. The 90% success metric measures only that some contact with a method exists, not that it is correct, which allows a high-looking launch with wrong recommendations. The 80% pilot threshold means 1 in 5 may be wrong, and a wrong ministry contact is a diplomatic incident, not a mere inconvenience. |
| C4 | A1 | REVISED | 1 | `ACCEPTED` | Returning exactly one 'recommended' contact plus two alternates implies a single right answer, but in practice sensitive outreach often needs the contact for a specific purpose, and a lead on one mission may be the wrong person for a different topic. Default country-level view ranks by mission link or recent engagement, so a coordinator opening the page without selecting context gets the contact for whichever mission is most active. They then reach out to that person about an unrelated or sensitive matter. Also, if the recommended contact was tied to a mission the viewer cannot see, the reason line becomes misleading. A one-line reason that looks authoritative will be trusted without checking. |
