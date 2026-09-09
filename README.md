# Review Pack — experimental Herdr plugin

Prepare one coding task for human review: its explicit brief, current Git diff,
and actual command receipts, with stale evidence clearly identified.

**Alpha 0.1.0.** Tested only on macOS with Python 3.14 (unit tests and a live Herdr
0.9.0 popup run); Linux and Python 3.11–3.13 are untested. No usage or quality improvements have
been measured. The plugin does not decide whether code is correct.

## A small workflow

1. Begin a task with a Markdown brief containing the requirement and expected checks.
2. Run your chosen verification commands through `check`.
3. Open Review Pack to inspect the brief, diff, command outcomes and logs.
4. If code changed after a check, its receipt is marked stale. Re-run the check
   explicitly if you need evidence for the new code.

No model API key, transcript scanning, telemetry, daemon or automatic command
execution. Existing agents can invoke the same CLI. The brief is an explicit
input, not an inferred summary of a conversation.

## Requirements

- Herdr 0.9.0+ for the pane; Python 3.11+, Git, macOS/Linux.
- A Git worktree with at least one commit. One current task per worktree.
- Optional `less` for scrolling. No Python packages or build toolchain required.
- No submodules in v0. Fingerprinting is one `git hash-object` pass per snapshot; large binary files are hashed by Git, not read into Python.

## Install

Public alpha source: [YmlyZA/herdr-review-pack](https://github.com/YmlyZA/herdr-review-pack).

```sh
herdr plugin install YmlyZA/herdr-review-pack      # add --yes when stdin is not a terminal
herdr plugin action invoke herdr-review-pack.open
```

If you previously linked a local copy, first run `herdr plugin unlink herdr-review-pack`.
This changes plugin registration only; saved task records remain.

### Local development install

From a Herdr-managed terminal:

```sh
herdr plugin link /absolute/path/to/herdr-review-pack
herdr plugin action invoke herdr-review-pack.open
```

The action opens the review popup for the invoking pane's directory. It refuses
if its pane is gone rather than guessing another pane. You can also open an
explicit repository:

```sh
herdr plugin pane open --plugin herdr-review-pack --entrypoint review --cwd /absolute/path/to/project
```

Optional binding in your Herdr config:

```toml
[[keys.command]]
key = "prefix+alt+v"
type = "plugin_action"
command = "herdr-review-pack.open"
description = "Prepare task for review"
```

Use `herdr server reload-config` after changing bindings.

## Record evidence

Use the same `REVIEW_PACK_STATE_DIR` for your shell and Herdr process if you
override it. Otherwise, in a normal shell set `--state-dir` to the exact
`HERDR_PLUGIN_STATE_DIR` printed in the panel so CLI and pane share records.
The standalone default is `~/.local/state/herdr-review-pack` (respects
`XDG_STATE_HOME`). State must be outside the reviewed worktree.

Put the wrapper on your PATH once (`bin/review-pack` inside the plugin directory):

```sh
ln -s /path/to/herdr-review-pack/bin/review-pack ~/.local/bin/review-pack
```

Then, from inside the project (options `--repo` and `--state-dir` go before the subcommand):

```sh
review-pack --state-dir /path/to/plugin-state begin --brief /path/to/task.md
review-pack --state-dir /path/to/plugin-state check --timeout 120 -- npm test
review-pack --state-dir /path/to/plugin-state pack
```

Coding agents will run checks through the wrapper if the repository tells them to;
see [docs/AGENTS-SNIPPET.md](docs/AGENTS-SNIPPET.md) for a paste-ready block.
`check` prints a one-line receipt summary on stdout and the full receipt JSON on
stderr, and exits with the wrapped command's own exit code.

`check` executes exactly the argv after `--`, in the repository root, with stdin
closed. Shell operators need an explicitly requested shell, e.g. `-- sh -c
'command1 && command2'`. Only run commands you intended to execute. It prints
the PID and log location immediately; inspect the file remotely with `tail -f`.
Ctrl+C or timeout stops the launched process group. Detached daemon processes
are outside this guarantee. Default timeout is 120 seconds; logs retain at most
2 MiB and show truncation. Launch errors, failures and timeouts are recorded.

In the popup: `b` begins a new task from a brief file, `r` creates and shows a
packet, `d` shows its diff, `l` shows a selected check log, and `q` closes it.
Checks are run through the CLI, never from inferred text or automatically in
the popup. Beginning another task archives the old records instead of reusing
their results. Each worktree has one active task; concurrent begin/check
operations are rejected.

## What the packet means

Each export contains `review.md`, `diff.patch`, and `packet.json`. Check logs
remain in the task directory and are referenced by absolute path. Exports are
local review material, not a self-contained share bundle. They may include
private requirements, paths, diffs, command arguments and logs; nothing uploads
them automatically. Do not attach a whole packet to a public issue without
reviewing it.

The diff is the entire staged + unstaged working tree against **current HEAD**,
not a last-turn or branch diff. Non-ignored untracked files are listed and
fingerprinted, but their contents are not embedded in the patch. Committed
changes are not shown. Use an existing diff tool for richer review.

| Snapshot relation | Meaning |
| --- | --- |
| `same-snapshot` | Fingerprints before and after the command match the current fingerprint |
| `stale` | The current fingerprint differs from the check's unchanged endpoints |
| `changed-during-check` | Fingerprints before and after the command differ |
| `unknown` | A required snapshot could not be read |
| `evidence-missing-or-modified` | The recorded log is missing or its digest changed |

Outcome and snapshot relation are separate: exit code 7 can be `same-snapshot`.
Exit 0 does not prove tests ran, coverage is sufficient, or the requirement was
met. No recorded checks displays **NOT PROVIDED**.

Fingerprint scope: HEAD, Git index, tracked and non-ignored untracked paths,
file contents, executable bits, symlink targets, and deletions. Ignored files,
installed dependencies, environment variables, services and time are excluded.
Snapshots are repeated samples, not atomic filesystem captures; temporary edits
between samples can be missed. Run checks while other agents are idle. Local
receipts are not tamper-proof attestations. Persisted files survive uninstall;
there is no automatic retention policy in v0.

## Remove

```sh
herdr plugin unlink herdr-review-pack
# For a future GitHub-managed install:
herdr plugin uninstall herdr-review-pack
```

Remove the optional keybinding. Source and evidence are separate; inspect the
state location before manually removing any saved tasks.

## Development and feedback

```sh
python3 -m unittest discover -s tests -v
```

Use [GitHub Issues](https://github.com/YmlyZA/herdr-review-pack/issues) for feedback.
Describe one task, your Herdr/OS/Python versions, which
step cost extra effort, and what you used instead. Include a small redacted
example if possible. Please do not send private transcripts or complete logs.
We want to learn whether the packet reduces the work of finding review evidence;
stars or command success counts are not acceptance metrics.

See [MVP scope](docs/MVP.md), [community references](docs/REFERENCES.md), and
[release gates](docs/RELEASE.md). MIT applies to this plugin directory only;
the parent experiment is not bundled into its release.
