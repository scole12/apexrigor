# NCAA results presentation incident — October 17–18, 2026

Status: public presentation restored; original executor and assigning lead attribution unresolved.
Owner: Scott Coleman. Recorded October 18, 2026. All times below are America/New_York.

## Owner requirement
Scott did not authorize reorganizing the results page during ratings work. Preserve the approved presentation: one cumulative season ATS tier table, one Totals tier table, one combined tier table, and the existing daily archive. Preserve current grading and historical source records.

## Verified evidence
- Website commit d9812daaa42338b954bb80b1612bb1a82fef93ab, October 17 at 12:36:32, replaced the cumulative tier tables with tables grouped by rating-policy identity, added policy labels/explanatory text, and expanded archive columns.
- 82a4653956291b30b0bbf72ca24239a8aa358481 at 12:37:40 added mobile labeling for that presentation.
- Droplet reflog records fast-forward integration at 12:38:26 and subsequent pushes through 12:39:47. GitHub's associated-PR lookup for d9812da returned no PR.
- The new tests/ncaaf_results_versions.test.cjs explicitly asserted version-separated presentation. Those tests encoded the new design; they did not establish owner authorization or preserve the previous design.
- Earlier branch commit 1c07bc507ff9092ba6532cb4b3b6b60773cd60ae at 11:24:17 also proposed grouping results by rating definition. Its metadata names APEX CoS and a Cursor co-author. This shows the idea existed earlier; it does not identify the session that instructed the later change.
- NCAAF commit 64349a1, titled "Persist NCAA V3 rating parity through cards and grading", occurred at 12:36:07. Temporal proximity supports investigating the same rating work, but alone does not prove a shared executor.
- The site repository's local Git configuration was independently read on October 18 and remains user.name=P2 Cursor, user.email=p2@example.invalid. Many unrelated publisher reflog entries reuse this identity. Therefore Git author/committer labels are NOT reliable proof that Cursor executed or directed this incident.
- Restore commit 531aefd6d9b01f0af495b32dbb821283f42bf900, October 18 at 11:36:07, records Claude as author with a Claude session link and reverses the presentation changes. Scott's supplied repair report identifies 1939b66 as removal of the test enforcing the unwanted design.
- Independent browser inspection on October 18 after 11:51 showed one ATS table, one Totals table, one combined table, the archive including October 17, and no repeated policy-version sections. This audit did not implement the restoration.

## Cause and accountability
Confirmed implementation rationale: expose historical rating definitions separately in the public results presentation.
Failure: ratings/data work expanded into an unrequested presentation redesign, and validation tested that redesign instead of preserving Scott's requested layout.

Original executing agent: NOT ESTABLISHED.
Original assigning/supervising session: NOT ESTABLISHED.
Original instruction authorizing the regrouping: NOT FOUND in the inspected records.
Do not blame Cursor, Opus, a human GitHub account owner, or another tool solely from a reusable Git identity.

Scott supplied a separate investigator's report identifying Desktop Commander remote process ancestry for the rating job. That identifies a claimed transport route, not the originating model or supervising session. This audit could not reproduce the historical process tree: PID 2460807 was absent when checked. The direct droplet connector was offline and the service reported inactive; authorized SSH via the Geekom remained available. This audit changed no access configuration.

The original lead owns explaining task scope and acceptance once that session is identified. The current repair lead owns preserving the restored presentation and reporting the unresolved attribution honestly.

## Required follow-through for Opus and all agents
1. Read this incident before further NCAA results work. Existing PROJECT_REQUIREMENTS.md protects the approved presentation and defines proportionate repair completion.
2. An instruction to fix data, ratings, grading or publication is not permission to change layout, sections, tables, columns or copy.
3. Record actual executor and accountable lead in the existing task record, with input commit, authorized scope and acceptance evidence. Never substitute Git config for execution attribution.
4. To close attribution, attach the original task/prompt and session or tool-call receipt linking it to the October 17 job. Keep attribution unresolved until that evidence exists.
5. Record future verified failures here or in a focused incident note with evidence, impact, cause, correction and unresolved items. Separate reported claims from independently verified facts; no speculative blame.
6. Do not reopen the completed layout repair, modify results, or launch new infrastructure to address this incident.
