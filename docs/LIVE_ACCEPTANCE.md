# Live Herdr acceptance (alpha)

No private project, account secret or real model call is needed. Use a Herdr
terminal on macOS/Linux with Python 3.11+, Git and Herdr 0.9.0+. The tests must
run inside the Herdr session being tested (`HERDR_ENV=1`). Do not attach to or
control someone else's session from outside it.

## What to report

- Herdr version, OS, Python version, local/SSH use, and `HERDR_ENV` (only this
  variable; do not dump the whole environment).
- Pass/fail for install, action open, packet, diff, logs, stale evidence,
  reopen, workspace isolation and unlink.
- For a failure: exact command, error text, plugin log excerpt and reproduction.
  No tokens, credentials, private source or full agent transcripts.
- If the visual popup cannot be inspected remotely, report that separately;
  do not claim a visual pass from exit status alone. A human can inspect it
  locally or through Screen Sharing. Text reports remain the primary result.

## Suggested agent handoff

Start your coding agent inside a Herdr-managed terminal and give it this task:

> Validate the public alpha at https://github.com/YmlyZA/herdr-review-pack in
> this Herdr session. First verify HERDR_ENV=1 and read the Herdr skill if
> available. Read docs/LIVE_ACCEPTANCE.md and docs/RELEASE.md. Use a new
> disposable Git worktree/project and plugin-owned state, never my business
> project. Install the plugin from GitHub (if already installed/linked, report
> its source before changing registration). Exercise the sequence below,
> record the version and each result, and stop on unexpected failures rather
> than papering them over. Do not stop the Herdr server or close panes you did
> not create. Report logs and resource paths; no public issue posting is needed.

## Test sequence

1. Record `herdr --version`, `python3 --version`, and the OS. Read the plugin
   source/manifest. Install using `herdr plugin install YmlyZA/herdr-review-pack`.
   If testing a local checkout instead, record that this does not verify the
   GitHub installation path.
2. Create a temporary directory containing a **new Git repository**, one
   tracked text file and an initial commit; put a Markdown task brief beside
   the repository. Use fixture-only Git identity, not global config changes.
   Open this repository in a disposable Herdr pane/workspace using the installed
   CLI's documented syntax. Preserve existing work and focus where possible.
3. Invoke `herdr plugin action invoke herdr-review-pack.open` from that pane.
   Verify the displayed repository is the fixture, not the plugin checkout or
   another focused client. Record the displayed shared state directory.
4. Press `b`, enter the brief's absolute path. Press `r`: the brief is visible
   and checks say NOT PROVIDED. Exit the pager with `q`, then the popup with `q`.
5. In the fixture's terminal, use the installed plugin's `review_pack.py` with
   explicit `--repo` and the recorded `--state-dir`. Run:
   `check -- python3 -c 'print("fixture check")'`.
   This is evidence of command execution only; it is not a real application test.
6. Reopen the popup. Press `r`: expect exit 0 and same-snapshot; `l`, choose
   the receipt, and verify the log says `fixture check`. Press `d` to inspect
   the diff. Clean diff is expected before editing.
7. Change the tracked text file. Reopen/regenerate (`r`): expect stale. Press
   `d`: the exact change appears. Re-run the explicit check, regenerate, and
   verify the new receipt is same-snapshot while the old one remains stale.
8. Record `check -- python3 -c 'raise SystemExit(7)'`. Expect exit 7, never a
   passing verdict. Optionally test a short timeout with an explicit sleep.
9. Close/reopen and verify records persist. Create a second disposable Git
   repository and open there: expect no task, not the first project's receipts.
10. Unlink/uninstall only this plugin if no prior installation needs preserving;
    otherwise restore/report the prior registration. Close only fixtures you
    created. Saved plugin evidence remains; report its location for later cleanup.

Treat manifest, focus/cwd, key input and popup restoration failures as release
blockers. The unit suite's mocked Herdr command is not a substitute for this
sequence. If a command stalls for 120 seconds, preserve PID and recent logs and
ask the operator to inspect possible macOS GUI prompts via Screen Sharing.
