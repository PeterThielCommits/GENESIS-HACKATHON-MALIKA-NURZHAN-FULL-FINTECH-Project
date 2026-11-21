# Decision log (append-only)

## D-05-01 — 2026-11-21 — PROVISIONAL, owner A0 unassigned
No organizer rules, samples or starter code are present on this branch. Master TZ is project-supplied, not organizer-issued. Record unanswered compatibility questions in QUESTIONS and issue #3. No official contract or rubric is asserted.

## D-05-02 — 2026-11-21 — PROVISIONAL, owner A2 unassigned
Implement a small standalone public-data environment and manually authored public test fixture to exercise phase-5 behavior without inventing upstream phase completion. Do not call its interface frozen or official. Earlier phases and the official gate remain blocked. No synthetic truth or scorer is created.

## D-05-03 — 2026-11-21 — PROVISIONAL, owner A0 unassigned
Valid submit is free; invalid submit consumes a step, and budget exhaustion truncates immediately. Close/open mode and finalization need organizer approval. The separate unmerged PR #1 proposes v1.0.0 schemas with conflicting finding and wire shapes; CR-05-01 records the required decision. Do not change its frozen contracts without an approved CR.

## D-05-04 — 2026-11-21 — PROVISIONAL, owner A2 unassigned
Cursor handles are HMAC-derived using a supplied key and stored only for the episode. The CLI uses a nonsecret fixed demo key. No process isolation is claimed. Calculator is omitted pending a decision on the organizer tool contract; PR #1 includes calc and must be reconciled.

## D-05-05 — 2026-11-21 — PROVISIONAL, owner A0 / A2 unassigned
The unmerged Phase 4 branch `arena/d94e8b76-genesis-hackathon-malika-nurzh` at `e7407843f9daf4f133ad7d1f032969713f7dd54e` defines a competing contract and public episode serialization. Without adopting or changing its frozen schemas, support its JSONL accounts and object balances/calendar at the loader boundary, and use `pair@effective_date` for accessing its FX rows. Retain legacy local fixture compatibility. Reject both account encodings together and hardlinked public files. This is a provisional adapter for public data only, not the official protocol. PR #1 and Phase 4 contract differences remain unresolved (CR-05-01). Independent review and organizer approval are still required.
