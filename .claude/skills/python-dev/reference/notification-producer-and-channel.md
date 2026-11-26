# Notification producer coverage and channel retry

Framework-agnostic. Load when a backend write should notify (push, email, SMS, in-app feed) or when a delivery retry is added. Client payload/allowlist rules stay in `flutter-mobile/reference/flutter-security-client-trust.md` §8. Outbox mechanics stay in `pubsub-firestore-patterns.md` and `reliability-idempotency-retries-outbox.md`.

## Iron Law

**A notification is covered only when every writer of its field stages it, every hop to the user is durable, and it is still true when it is delivered.**

**Never resend a message whose provider acceptance is unknown, and never retry without re-deriving the recipient.** A duplicate or wrong-person send cannot be recalled.

**A provider `202` / `200` is not delivery.** Unsupported checks are `NOT EXECUTED`, never `PASS`.

## Producer checklist (every change that writes a notifiable field)

1. **Inventory writers.** Grep every assignment / status transition of the field. One green producer test on the happy path does not cover a second writer.
2. **Stage in the same transaction** as the business write (Pattern B outbox). Fire-and-forget (Pattern A) is only for informational events the caller does not depend on.
3. **Durable hops.** Each hop (outbox → worker → provider → device/inbox) has an idempotency key and a recorded outcome. A crash between hops must retry the **same** key, not a new send.
4. **Still true at delivery.** Re-read canonical state before send. A cancelled job must not notify “en route”.
5. **Revalidate the recipient** at send time (current owner, not the id captured at enqueue). Account switch, reassignment, and revocation are first-class tests.
6. **Absence test.** A writer that should **not** notify has a test that the outbox row is missing.

NestJS / Java: the same six checks apply to the owning service’s outbox or inbox table — do not add a second pipeline.

## Channel retry (push, email, SMS)

| Provider outcome | Action |
|---|---|
| Accepted (`PROVIDER_ACCEPTED`) | Do not resend. Observe webhooks / receipts for delivery. |
| Unknown (`ACCEPTANCE_UNCERTAIN` — timeout, 5xx with no body, dropped connection after write) | **Do not retry the send.** Claim the attempt, alarm, reconcile from provider state. |
| Rejected (4xx that will not change) | Do not retry. Record `REJECTED`. Fix payload or drop. |
| Unregistered / unknown token | Delete the address; do not retry that destination. |
| Transient (429, retry-after) | Retry **the same idempotency key** after the delay, after re-deriving the recipient. |
| In-app feed (DB/Firestore write, no provider hop) | Same idempotency key; do not insert a second row on retry. A client read is not a second send. |

Never open a second sender (a second FCM project, a second “just this email” client) for the same product event.

## Email QA floor (when the product sends mail)

| Tier | What it proves | Not a pass |
|---|---|---|
| Q1 CI | Template + recipient rules, no live provider | Hitting the network |
| Q2 sandbox | Provider accepts in sandbox / test mode | Inbox placement |
| Q3 staging | One controlled send per role to a sink or approved mailbox | Production send |
| Q4 preview | Spam/link tooling the provider actually supports | Claiming an unsupported check as PASS |

No live provider request without that tier’s explicit approval.

## SMS floor (when the product sends SMS)

Same uncertain≠retry rule. Signed webhooks. Honour STOP/consent. Do not treat Twilio (or any) `201` as handset delivery.

## Tests that must exist for a new producer

- Happy path: business row + outbox row in one transaction
- Second writer of the same field also stages (or is documented as not-a-notifier with an absence test)
- Delivery after cancel / reassign is suppressed or rewritten
- Uncertain acceptance is not retried (control: a timeout after the HTTP write)
- Duplicate idempotency key → one side effect
