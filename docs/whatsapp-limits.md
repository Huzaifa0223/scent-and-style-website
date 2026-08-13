# WhatsApp message payload limits

**Status: not yet measured. `WHATSAPP_MESSAGE_MAX_CHARS` is an unverified, deliberately
conservative placeholder — not a verified limit.** This is a human task (see
`specs/state.md` → *Human tasks*), not something this agent can do: it requires real
devices and real WhatsApp clients.

## What's actually configured today

`StoreSettings.whatsapp_message_max_chars` defaults to **1000** characters of raw message
text (measured before URL-encoding into the `wa.me/?text=` query parameter). This number
was chosen because it is comfortably below every publicly-documented concern about
`wa.me` URL length, at the cost of triggering the truncation path (`…and N more items`)
more eagerly than a verified number might require. It has not been checked against any
real browser or WhatsApp client. Do not treat it as correct — treat it as a safe
placeholder that errs toward truncating too early rather than silently dropping content
past an unknown real ceiling.

## What needs to be measured

For each of the three targets §21 names, find the point at which a `wa.me/?text=...` link
stops opening WhatsApp with the full message pre-filled (truncates silently, fails to
open, or opens with an error):

- [ ] **Android Chrome** — ceiling: ___________ characters (raw message text)
- [ ] **iOS Safari** — ceiling: ___________ characters (raw message text)
- [ ] **WhatsApp Web** (desktop browser, `web.whatsapp.com`) — ceiling: ___________ characters

### Suggested method

1. Use `notifications.whatsapp.message_builder.build_order_confirmation_message` (or a
   throwaway script calling it directly) to generate messages of increasing length —
   e.g. orders with 5, 10, 20, 40, 80 items — with `StoreSettings.whatsapp_message_max_chars`
   temporarily set high enough that none of them truncate.
2. For each length, build the `wa.me` URL via `notifications.whatsapp.channel.WhatsAppLinkChannel`
   and open it on each target (a real Android phone with Chrome, a real iPhone with
   Safari, and a desktop browser at web.whatsapp.com).
3. Record the message length at which the pre-filled text first gets cut off, or the
   link stops working at all. That's the ceiling for that target.
4. The safe default is the **smallest** of the three ceilings, with a margin — not their
   average.

## Once measured

Fill in the table above, then update `StoreSettings.whatsapp_message_max_chars`'s
`default=` in `store/models.py` (a new migration — `AlterField`, adjusting only the
default) to the real conservative number, and update this file's "Status" line at the
top to say when and by whom it was verified.
