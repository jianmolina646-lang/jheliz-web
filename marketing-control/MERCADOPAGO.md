# Mercado Pago / Yape — WhatsApp sales

New PEN orders use a hosted Checkout Pro preference after the customer replies
YAPE, MERCADOPAGO, QR or /pagar. Binance remains manually verified. Existing
Lemon orders and its verifier remain intact; do not migrate an already-selected
payment silently. Mercado Pago supports Yape for the configured Peru seller;
the hosted checkout controls which methods are shown to each customer.

## Secrets and activation

Only the marketing API and worker use `/run/secrets/mercadopago-access-token`
and `/run/secrets/mercadopago-webhook`. Never commit these files. Production
binds `/opt/jheliz-marketing-secrets` read-only, with files owned by UID 1000,
mode 0400. `/run/secrets/mercadopago-enabled` must contain `true` to offer new
links. Disabling it does not stop verification of existing MP orders.

Webhook: `https://marketingjhelizxyz.online/webhooks/mercadopago/`, event
**Pagos (legacy)** (`payment`). The old exact path on ecormecejhelizstore.com
is proxied directly to this bot, never to the inventory application. No
credential or payment processing is added to the inventory panel.

## Guarantees and limitations

- Signed webhooks durably enqueue the payment ID before returning HTTP 200.
- The worker fetches canonical `/v1/payments/{id}`; it never approves from the
  callback body or a checkout return URL. A search reconciler recovers missed
  callbacks every minute (subject to batch load and provider availability).
- Approval requires the live seller 1804582803, PEN, exact gross amount, the
  bot order external reference, approved status, and no refunded amount.
- Database transactions serialize approvals. One payment cannot deliver two
  orders. Replayed notifications cannot duplicate stock allocation/renewal.
- Missing stock retains a confirmed payment for retry and emits an operator
  event. A cancelled order or second payment requires operator review.
- Refund/status changes after approval are recorded and raise an event; no
  automatic refunds or credential revocation are performed.
- Once a link is issued, changing provider or customer self-cancellation is
  blocked. Links expire after two hours; ask support after expiry. A preference
  creation timeout may create an unused extra preference with the same order
  reference; no link is sent before its response is safely persisted.
- Renewal approval follows the pre-existing owner-confirmed upstream renewal
  policy; this does not itself pay/renew a Netflix/Disney subscription.
- Delivery uses the existing outbox. Ambiguous WhatsApp sends remain in review
  rather than sending credentials again automatically.

## Verification

`node --test tests/mercadopago.test.js` covers signatures, amounts, identity and
HTTP errors. `RUN_MP_TEST=1 node --test tests/mercadopago-integration.test.js`
requires the explicitly isolated database `marketing_mp_test`; it resets only
that test database. Tests cover replay, concurrency, provider switching,
amount mismatch, no stock, cancellations and renewal idempotency.

Creating a technical preference is not a payment. A customer-approved real
purchase is still required to prove the end-to-end Yape/WhatsApp delivery.

API references:
- https://www.mercadopago.com.pe/developers/es/reference/online-payments/checkout-pro-preferences/create-preference/post
- https://www.mercadopago.com.pe/developers/es/docs/your-integrations/notifications/webhooks
