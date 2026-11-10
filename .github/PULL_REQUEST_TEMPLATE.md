## What this changes

<!-- What does this pull request do, and why? Link the issue it closes. -->

## How it was verified

<!--
The checks that ran, and what they showed. "The CI is green" is not a
verification — name the check and what it proved.
-->

- [ ] The tests that cover this pass, and I have run them locally.
- [ ] `ruff check .` passes.
- [ ] `pytest -q` passes for the root package.
- [ ] `pytest -q` passes for `packages/helix-core`.
- [ ] `bandit -c pyproject.toml -r . -q -ll` passes.
- [ ] The two distributions still build and are still cleanly split
      (`python scripts/verify_distributions.py`).

## Notes for the reviewer

<!--
Anything that is hard to see in the diff: a trade-off made, a risk taken,
something deliberately left out and why.
-->
