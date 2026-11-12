#!/usr/bin/env bash
# Put the demo back to its recorded state.
#
# Several of the demo journeys change data on purpose -- signing out, emptying
# the wallet, linking a bank. Run this between takes and the app is exactly
# where it started: four cards, two banks, $234.21 earned and $65.64 missed.
#
# Close Expo Go first. The running app writes to these files, and a reload in
# the middle of a restore can put half the old state back.
set -euo pipefail

cd "$(dirname "$0")/.."
SNAP="data/demo-snapshot"

for f in wallet profile ledger plaid plaid_transactions funding; do
  cp "$SNAP/$f.json" "data/$f.json"
done

cd data && shasum -a 256 -c "demo-snapshot/CHECKSUMS.txt"
echo
echo "Demo state restored. Reopen Expo Go."
