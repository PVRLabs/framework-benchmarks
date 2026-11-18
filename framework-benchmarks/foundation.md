# Portfolio correctness contract

## Shared correctness requirements

Use HTTP checks plus independent SQL assertions on a disposable PostgreSQL DB:
seed formula/counts/marker; all routes and decimal totals; add/update/idempotent
assignment/delete/empty portfolios; invalid requests and unknown users; latest,
history bounds and replay wrap; invalid-batch rejection and failed-write rollback;
readiness before ingestion, DB outage and recovery; persistent edits/prices after
restart without reseeding. Adapt the reference database and restart tests into
shared checks; existing H2 tests alone do not establish PostgreSQL correctness.

Exercise concurrent absent-holding insert/update/delete and different-symbol edits
for one user, checking no duplicates or partial writes. Use controlled overlapping
transactions to establish blocking/commit order rather than guessing final values
from HTTP submission order. Verify different-user independence and snapshot
valuation during quote commits. Never compare independently timed portfolio and
valuation calls as if prices could not change between them.
