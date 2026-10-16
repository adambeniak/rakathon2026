<!-- WHO: anyone during a rebase · TOOL: Claude Code (Sonnet) · MODE: normal -->

You are resolving conflicts of an in-progress `git rebase origin/main` on my feature branch. Goal: keep BOTH sides'
intent; never silently drop behaviour from main.

1. `git status` and list conflicted files. For each file classify:
   - generated (`contracts/openapi.json`, `frontend/src/lib/api/schema.d.ts`, `uv.lock`, `pnpm-lock.yaml`):
     take main's version with `git checkout --ours <file>` (during a rebase "ours" = main, "theirs" = my commit),
     then regenerate (`make contract`, `uv lock`, `pnpm install`) after the rebase step.
   - registries/lists (routes, routers, i18n index, Makefile, docker-compose): union of both sides.
   - logic: explain both versions in 2 lines each, propose the merged version, apply it.
2. Show me a short table: file · type · resolution, before running `git add` and `git rebase --continue`.
3. After the rebase: `make check` (and `make eval` if extraction/consistency changed). If tests fail, fix only what the
   merge broke and say so.
4. Never run `git push --force`; I will push with `--force-with-lease` myself after reviewing.
