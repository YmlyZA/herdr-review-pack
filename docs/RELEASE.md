# Alpha release gates

## Current state

Publishing target: https://github.com/YmlyZA/herdr-review-pack (public alpha).
Local CLI and panel-script tests pass on macOS/Python 3.14.7.

Live run on 2026-09-09, Herdr 0.9.0, macOS, in a dedicated `dev` Herdr session
(`herdr --session dev`), driven through the CLI (`plugin link`, `plugin action
invoke`, `plugin pane open --placement split`, `pane send-text/send-keys/read`):
link, action invoke with correct pane cwd, begin from brief, NOT PROVIDED,
same-snapshot after a CLI check using the printed shared state directory, log
view, stale after editing a tracked file, diff showing the change, exit-7 check
recorded as exit 7 / same-snapshot, records persisting across reopen, second
repository isolated, unlink clean. This run found and fixed one release blocker:
pane commands execute with cwd = the reviewed repository, so the manifest must
reference `panel.sh` through `$HERDR_PLUGIN_ROOT` (a relative path made the pane
exit immediately). The default `popup` placement was not inspected visually
(no TUI client was attached to the dev session); the same pane command was
exercised with `split` placement. Linux and Python 3.11–3.13 remain untested.
Marketplace discovery must be confirmed separately after publication.

## Before promoting beyond alpha

- Run `python3 -m unittest discover -s tests -v` on macOS and Linux, Python 3.11+.
- From a Herdr-managed terminal, link this directory, invoke the open action in
  a disposable Git workspace, begin from a brief, record a harmless check in
  another shell using the displayed state directory, and inspect `r`, `d`, `l`.
- Edit a tracked file, regenerate, confirm stale; close and reopen to verify
  persistence. Invoke from another workspace and confirm isolation.
- Verify `q` restores the underlying pane; unlink and remove the optional binding.
- Verify manifest validation in the installed Herdr version. Unit mocks are not
  a substitute for this test.
- Keep the public repository limited to plugin source/docs/tests/license.

The Herdr v0.9.0 plugin documentation describes marketplace discovery via a
public GitHub repository carrying topic `herdr-plugin`, with a manifest in its
default branch (root or subdirectory). For a dedicated repo, use its root;
for the parent repo, the install suffix is `/plugins/herdr-review-pack`.
Verify discovery after publication; indexing is not guaranteed by a successful
push. Public alpha target: `herdr plugin install YmlyZA/herdr-review-pack`.

## Draft listing description

Review Pack prepares a coding task for human review: explicit requirements,
the current Git diff, and local command receipts tied to code snapshots. It
marks stale or missing evidence without treating a successful command as code
acceptance. Experimental, local-only, Python stdlib, no model key required.

## Recovery

Unlink/uninstall the plugin and remove its optional binding. Saved receipts
remain outside the code checkout. No daemon, startup hook or automatic test
runner needs stopping. An explicitly launched check prints its PID and timeout;
Ctrl+C terminates its process group.
