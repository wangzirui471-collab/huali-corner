# Complete Cloudflare functionality repair

Goal: repair every existing frontend mode and action against the cloud backend, preserving data, roles, API contracts and simulation rules.

Design authority: existing 2026-10-17 Cloudflare design, current local domain services, and user's explicit request to fix every mode and inspect each one. This is completing existing behaviour, not adding unrelated features.

- [ ] Inventory every frontend endpoint/method and every page entry, with authenticated role expectations.
- [ ] Shared D1 conditional batch: failed in-transaction guards must actually roll back, never use an after-the-fact expect as rollback.
- [ ] Catalog/profile/media: upload, publish, edit profile/avatar, product governance, reactions, offers.
- [ ] Community: posts/comments/wants, rooms, membership, private/support chats, messages, blocks and moderation.
- [ ] Support/staff: ticket details and lifecycle, refunds/reviews, staff/roles, governance, dossier, audit, backup.
- [ ] Trade: atomic reserve/order/ledger, cancellation, delivery/receipt, changes, timers and seller restriction checks.
- [ ] Authentication compatibility: correct old/new salt during change-password, registration validation, deactivation, staff KDF.
- [ ] Register all handlers and enforce method coverage for every frontend request; do not return fake empty data or hide broken entries.
- [ ] Synthetic local D1/R2 browser walkthrough for buyer, seller, support, admin, developer in desktop/mobile sizes.
- [ ] Full tests and independent review; record remaining failures by name.
- [ ] Deploy to existing Worker/resources, read-only live verification, preserve all actual accounts/media/orders.

Rulings: use existing settings NOT NULL constraint for an ephemeral failure-only batch guard; successful guards create no rows and require no schema migration. All business writes including conditional guards execute in one D1 batch. Domain modules have exclusive owners; root alone integrates api.py/d1.py/worker.py. Tests never initialize or write production data. Existing dirty source and local files remain preserved.
