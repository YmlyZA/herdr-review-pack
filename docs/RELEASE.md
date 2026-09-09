# Alpha release gates

## Current state

Publishing target: https://github.com/YmlyZA/herdr-review-pack (public alpha).
Local CLI and panel-script tests pass on macOS/Python 3.14.7. No live Herdr
integration or Linux run has been claimed. Publication is for early testing;
do not describe this alpha as fully validated. Marketplace discovery must be
confirmed separately after the repository topic is set.

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
