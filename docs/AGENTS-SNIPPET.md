# Making agents record receipts

Review Pack only knows about checks that were run through it. Humans rarely
type the wrapper; coding agents will, if the repository tells them to. Paste
the block below into the repository's `AGENTS.md` (or `CLAUDE.md`) and adjust
the commands. Keep it short: agents follow concrete instructions, not policy.

```markdown
## Verification receipts

This repository records verification runs with Review Pack so the reviewer can
see which checks ran against which code. When you run tests, lint, type checks
or builds, run them through the wrapper instead of directly:

    review-pack check -- npm test
    review-pack check -- npm run lint

Rules:
- Run the check after your last edit. A receipt taken before further edits is
  marked stale and does not count.
- The wrapper exits with the command's own exit code; a non-zero exit is the
  check failing, not the wrapper failing. Read the log path it prints.
- Do not paraphrase results in your summary; say "see receipt <id>" instead.
- If the task started with a brief, do not run `review-pack begin` again.
```

## Installing the `review-pack` command

The wrapper lives at `bin/review-pack` inside the plugin directory. Put it on
`PATH` once:

```sh
# Herdr-managed install (path printed by `herdr plugin list`):
ln -s "$(herdr plugin config-dir herdr-review-pack 2>/dev/null || echo /path/to/herdr-review-pack)/bin/review-pack" ~/.local/bin/review-pack
# or from a clone:
ln -s /absolute/path/to/herdr-review-pack/bin/review-pack ~/.local/bin/review-pack
```

If `herdr plugin config-dir` prints the config directory rather than the source
directory, use the source path shown by `herdr plugin list` instead.

## Sharing state between the agent's shell and the Herdr popup

The popup prints its shared state directory. Export it in the shell the agent
runs in, e.g. in the repository's direnv/`.envrc` or the agent's startup:

```sh
export REVIEW_PACK_STATE_DIR=/Users/you/.local/state/herdr/plugins/herdr-review-pack
```

Both sides then read and write the same task and receipts. The state directory
must stay outside the reviewed worktree.
