---
name: shared-repo-branch-isolation
description: Use when a push is rejected or branch flips mid-commit.
category: git-workflow
---

# Shared repo: isolate branch work, never force-push

- Before each commit run `git branch --show-current` and `git status -sb`. If the branch is not the one you started on, stop: another session may have switched the folder.
- Do feature-branch work in its own worktree (`git worktree add ../REPO-BRANCH BRANCH`) and commit there. Leave the main folder on `main`.
- If a push is rejected as non-fast-forward, do not force it. Run `git fetch`, compare `git log --oneline -3 origin/BRANCH` with HEAD, and add a new commit on top. Forced pushes are denied by the auto-mode classifier.
- If the remote commits already fix the same concerns (a review bot's autofix or another contributor), adopt the remote: `git branch keep-NAME HEAD` to save your copy, then `git reset --hard origin/BRANCH`. Re-run the tests on the remote version and add only the real gaps as a new commit. Never discard your commit without saving it to a side branch first.
- Do not `git commit --amend` a commit that has already been pushed; add a new commit instead.
- Recovering work that landed on the wrong branch: find the commit in `git reflog`, restore the branch with `git branch -f BRANCH HASH`, and reset the wrong branch with `git reset --keep origin/main`. Then confirm `git diff HASH HEAD --stat` is empty before pushing.
