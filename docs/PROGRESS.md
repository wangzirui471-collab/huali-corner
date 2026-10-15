# Ledger — plan: docs/superpowers/plans/2026-10-15-pilot.md
Ruling: user explicitly asked to make software now; execute locally without more design approvals. No external publish or paid actions.
Ruling: use standard-library Python + SQLite + JS rather than proposed Next.js; existing runtime has no Flask/pytest, reduces setup cost. Cost if changed later: port API implementation.
Ruling: same-seller combined delivery charged once at maximum per-item fee; displayed before checkout. Cost if unsuitable: revise delivery policy before real transactions.
Ruling: 24h auto receipt starts only after buyer acknowledges handover; seller alone cannot start funds release. Disputes freeze settlement. Cost: buyer inaction may require staff mediation.
Pre-flight: all clients consume JSON API; identity is bearer session, public user summaries omit phone; all money amounts integer cents; domain transactions own DB writes.
Task 1: complete — SQLite persistence, OTP/session, upload/listing/ownership; domain tests green.
Task 2: complete — combined fee, stock race, payment/refund/settlement journal, complete media backup and reconciliation; regression tests green.
Task 3: complete — posts/comments/private/group chat and 500-member split; privacy/block/idempotency tests green.
Task 4: complete — API-backed responsive browser UI, actual generated-photo upload, sale/refund browser flow passed.
Task 5: native code and operations docs written; WeChat tooling/device verification unavailable, explicitly unrun.
Final review: independent reviewer identified five Important findings: native logout leak, native message cursor, conflict-of-interest by product-only complaint, non-operative reschedule, missing native seller delivery instructions.
Final: fixed native account state/in-flight/cursor — Node regression tests, old logout check RED→GREEN, cursor checked beyond100.
Final: fixed product/transaction conflict — test_admin_cannot_judge_own_product_or_product_linked_purchase RED→GREEN.
Final: fixed operative reschedule — test_schedule_confirmation_and_structured_reschedule RED→GREEN.
Final: fixed native seller fulfillment details — tests/native_order.test.js RED→GREEN.
Ruling: users may verify handover separately from product acceptance, and only then start24h auto-receipt; reduces unilateral seller abuse, but inactive buyer can require support.
Ruling: 4yuan is suggested minimum only, no hard floor; preserves low-value and free transfer.
Deferred minors: full group member administration interface; advanced support and reconciliation primarily on desktop web; no WeChat-tool/device validation available.
Final verification: 24 Python domain/HTTP tests passed; native privacy/session/cursor and seller-order rendering regression tests passed. Browser exercised real image upload, persistence-backed publish/favorite/checkout/payment/refund/group chat and responsive layout without JavaScript errors.
Backup restoration: actual ZIP extracted to a new directory; database reopened and image paths rebound successfully.
No external publication or purchase; original /workspace/- checkout unchanged. WeChat tool compilation and real-device checks remain unrun.
