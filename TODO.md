# TODO

Debt is recorded here, with the stage that incurred it. Never `# TODO` in shipped code — see
CLAUDE.md.

## Debt

- [Stage 2] `ProductImage` derivative generation (thumb/card/full, WebP+JPEG) runs synchronously
  inside `save()`. Deliberate per requirements §2.5 — a merchant uploading a handful of images
  tolerates a ~1-2s save; a broker/worker process to avoid that cost doesn't pay for itself yet.
  Revisit if CSV bulk import (Stage 16) makes many-image imports painfully slow.
