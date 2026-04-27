# Feint Precision Experiment

## Goal

Determine whether Feint changes a shared precision or accuracy value, and whether Beam, Damage, and Support routines read that modified value.

## Experiment Design

1. Capture baseline RAM state before Feint is used.
2. Use Feint and identify RAM addresses that change immediately after the action resolves.
3. Set BGB watchpoints on candidate RAM addresses.
4. Use Beam, Damage, and Support cards in controlled cases.
5. Check whether their routines read the modified value.
6. Repeat with and without Feint to separate real dependencies from unrelated turn-state changes.

## Notes

No conclusions yet. This file is a plan for validation, not evidence.
