# Git history credential remediation

The application repository previously contained credentials in reachable Git
commits. Rotating every exposed credential is mandatory; rewriting history is
only the second half of the response.

## Prepared workflow

1. Make a fresh mirror clone. Never run history rewriting against a dirty
   developer checkout.
2. Generate a private, non-redacted Gitleaks JSON report in a mode-0700
   temporary directory.
3. Convert findings into a mode-0600 `git-filter-repo --replace-text` file with
   `.github/scripts/build_filter_repo_replacements.py`.
4. Run `git filter-repo --sensitive-data-removal --replace-text ...` in the
   mirror clone.
5. Run Gitleaks against all rewritten history. The result must be zero.
6. Create a bundle backup of the rewritten repository before replacing the
   remote refs.

The report and replacement file contain live historical secrets. They must
never be committed, attached to tickets, or copied into chat. Delete the
temporary directory after validation.

## Remote cutover

Schedule a maintenance window and stop merges before replacing remote refs.
Record the old and new `main` commit IDs, force-push rewritten branches and
tags using explicit refspecs, and ask every contributor to make a fresh clone.
Old forks, CI caches, release artifacts, and local clones remain independent
copies and must be deleted or remediated separately.

After cutover, change the CI secret scan from a current-files scan to a full
history scan. Do not add historical findings to an allowlist merely to make
the gate pass.
