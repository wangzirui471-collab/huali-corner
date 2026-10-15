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

## Marketplace visual redesign (2026-10-15)
User requested a closer reference to their Xianyu/Zhuanzhuan screenshots. Replaced sidebar/large promotional hero with top search, channel icons, compact campus promos and photo-first feed; increased card typography and highlighted delivery-aware prices. Bright yellow/black marketplace accents replace the muted green palette.
Original AI-generated contact-sheet asset is used only for clearly labeled seeded demo goods; real uploads retain original photos. Native source theme/home/detail updated, not tool/device validated.
New UI acceptance script verifies search at top, early product feed, real category/search navigation, details, and no horizontal overflow at375/390/768/1440. Existing purchase-flow locator updated to account for visible pickup badge inside item title.

## Windows compatibility correction (2026-10-15)
User screenshot reproduced an HTTP500 caused by Path.is_relative_to on Python before3.9. Regression first failed with the same missing-method exception; login's str.removeprefix had the same compatibility issue. Static serving now compares resolved paths using os.path.commonpath, preserving containment, sibling-directory and symlink escape protection. Bearer parsing uses startswith/slicing. College JSON explicitly uses UTF-8 for Windows system-default encoding independence.
Verification: 28 domain/HTTP tests pass, including missing-method simulation, private-path rejection and non-UTF8 default simulation. Browser upload/publish, favorite, checkout, simulated payment, dispute/refund, group chat and mobile layout passed without JS errors. Runtime is Python3.12; older Windows interpreter/device execution remains unrun. README includes one-file update instructions that preserve var/ and separate the unrelated pip proxy failure from this bug.

## Shareable public visual demo (2026-10-15)
User chose an isolated public demo for showing classmates, without real phone or address collection. Bounded implementation reuses existing web screens; export script opens only a fresh temporary seeded DB and copies a fixed static-file allowlist. Read-only snapshot adapter supports product/category/search/price/profile/community views. Private routes and write actions show explanations; no account, address, message or upload forms are offered. Original Python simulation remains separate.
No hosting credentials found among Netlify/Vercel/Cloudflare/Render/Railway bindings, and no hosting connector is available. Prepare tested static ZIP and upload source/package to existing private GitHub repo; manual hosting account upload is the remaining external step. No public URL is generated or claimed yet. Exact Netlify Drop instructions and deployment/privacy boundaries are in docs/PUBLIC_DEMO.md.
Independent review found no Critical/Important issue and one Minor: seeding artwork modified source assets during export. Fixed by directing seed artwork into the temporary directory; regression reproduced the source write before the fix. Export now leaves the checkout artwork untouched. Final checks: 31 Python tests; static public browser smoke; original transaction browser smoke; visual layout smoke; native client tests and JS syntax passed. No external deployment performed; provider page connectivity from this cloud was not established.
