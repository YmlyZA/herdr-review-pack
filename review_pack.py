#!/usr/bin/env python3
"""Local, explicit review preparation. Python stdlib only; never runs inferred commands."""
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import selectors
import shlex
import signal
import stat
import subprocess
import sys
import time
import uuid

VERSION = "0.1.0"
LOG_LIMIT = 2 * 1024 * 1024


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    proc = subprocess.run(["git", "--no-pager", "-C", str(repo), *args],
                          capture_output=True, timeout=30,
                          env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    if proc.returncode:
        raise ValueError(proc.stderr.decode(errors="replace").strip())
    return proc.stdout


def root(path):
    return Path(os.fsdecode(git(path, "rev-parse", "--show-toplevel")).strip()).resolve()


def snapshot(repo):
    """Conservative content fingerprint; fail rather than silently skip unsupported data.

    File contents are hashed by one `git hash-object --stdin-paths` call (no
    object-database writes, no Python-side reads), so a snapshot costs roughly
    one `git status`. Symlinks hash their target string; deletions are explicit.
    """
    head = git(repo, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    index = git(repo, "ls-files", "--stage", "-z")
    if any(row.startswith(b"160000 ") for row in index.split(b"\0")):
        raise ValueError("Submodules are unsupported in v0; no freshness claim can be made.")
    paths = sorted(set(git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0")) - {b""})
    entries = {}
    regular = []
    for raw in paths:
        p = repo / os.fsdecode(raw)
        try:
            st = p.lstat()
        except FileNotFoundError:
            entries[raw] = (b"deleted", b"")
            continue
        mode = str(stat.S_IFMT(st.st_mode) | (st.st_mode & 0o111)).encode()
        if stat.S_ISLNK(st.st_mode):
            entries[raw] = (mode, os.fsencode(os.readlink(p)))
        elif stat.S_ISREG(st.st_mode):
            entries[raw] = (mode, None)
            regular.append(raw)
        else:
            raise ValueError("Unsupported tracked/untracked path: " + str(p))
    if regular:
        # --stdin-paths is newline separated; a path containing a newline gets its own call.
        batch = [r for r in regular if b"\n" not in r]
        single = [r for r in regular if b"\n" in r]
        hashes = []
        if batch:
            hashes = hash_paths(repo, b"\n".join(batch) + b"\n", stdin_paths=True)
            if len(hashes) != len(batch):
                raise ValueError("Worktree changed while hashing; retry after the writer stops.")
        for raw in single:
            hashes.append(hash_paths(repo, None, path=raw)[0])
        for raw, blob in zip(batch + single, hashes):
            entries[raw] = (entries[raw][0], blob)
    h = hashlib.sha256(b"review-pack-v2\0" + head.encode() + b"\0" + index)
    for raw in paths:
        mode, content = entries[raw]
        for part in (raw, mode, content):
            h.update(len(part).to_bytes(8, "big")); h.update(part)
    return {"digest": h.hexdigest(), "head": head, "files": len(paths)}


def hash_paths(repo, stdin, stdin_paths=False, path=None):
    argv = ["git", "--no-pager", "-C", str(repo), "hash-object", "--no-filters"]
    argv += ["--stdin-paths"] if stdin_paths else ["--", os.fsdecode(path)]
    proc = subprocess.run(argv, input=stdin, capture_output=True, timeout=300,
                          env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    if proc.returncode:
        raise ValueError("git hash-object failed: " + proc.stderr.decode(errors="replace").strip())
    return proc.stdout.split()


def stable_snapshot(repo):
    first, second = snapshot(repo), snapshot(repo)
    if first != second:
        raise ValueError("Worktree changed while reading; retry after the writer stops.")
    return second


def state_base(override=None):
    return Path(override or os.environ.get("REVIEW_PACK_STATE_DIR") or
                os.environ.get("HERDR_PLUGIN_STATE_DIR") or
                Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "herdr-review-pack").expanduser().resolve()


def store_for(repo, base):
    if base == repo or repo in base.parents:
        raise ValueError("State must be outside the reviewed worktree.")
    p = base / digest(os.fsencode(str(repo)))[:24]
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    return p


def write_json(path, value):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as f:
            os.chmod(temp, 0o600)
            json.dump(value, f, ensure_ascii=True, indent=2)
            f.write("\n")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


@contextlib.contextmanager
def lock(store):
    with (store / "operation.lock").open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another begin/check operation is active for this worktree.")
        yield


def task_dir(store):
    if not (store / "current.json").exists():
        raise ValueError("No task yet. Use begin --brief /path/to/task.md, or [b] in the panel.")
    current = json.loads((store / "current.json").read_text())
    task_id = current["task_id"]
    if not isinstance(task_id, str) or len(task_id) != 32 or any(c not in "0123456789abcdef" for c in task_id):
        raise ValueError("Invalid task identity in local state.")
    return store / task_id


def begin(repo, store, brief):
    source = Path(brief).expanduser().resolve()
    if source.stat().st_size > 128 * 1024:
        raise ValueError("Brief exceeds 128 KiB.")
    text = source.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("Task brief is empty.")
    with lock(store):
        task_id = uuid.uuid4().hex
        folder = store / task_id
        folder.mkdir(mode=0o700)
        task = {"schema_version": 1, "id": task_id, "created_at": now(),
                "repo": str(repo), "brief": text, "brief_source": str(source),
                "brief_digest": digest(text.encode()), "start": stable_snapshot(repo)}
        write_json(folder / "task.json", task)
        write_json(store / "current.json", {"task_id": task_id})
        return folder


def stop_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait(timeout=5)


def run_check(repo, store, argv, timeout):
    if not argv:
        raise ValueError("Provide an explicit command after --.")
    with lock(store):
        folder = task_dir(store)
        task = json.loads((folder / "task.json").read_text())
        before = stable_snapshot(repo)
        run_id = uuid.uuid4().hex
        logfile = folder / (run_id + ".log")
        receipt = {"schema_version": 1, "id": run_id, "task_id": task["id"],
                   "brief_digest": task["brief_digest"], "argv": argv,
                   "cwd": str(repo), "started_at": now(), "before": before,
                   "after": None, "outcome": "interrupted", "exit_code": None,
                   "log": logfile.name, "log_truncated": False}
        proc = None
        started = time.monotonic()
        written = 0
        try:
            with logfile.open("xb") as log:
                os.chmod(logfile, 0o600)
                proc = subprocess.Popen(argv, cwd=repo, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        start_new_session=True)
                print(f"Check PID {proc.pid}; log: {logfile}; timeout: {timeout}s; Ctrl+C stops this check.", flush=True)
                with selectors.DefaultSelector() as sel:
                    sel.register(proc.stdout, selectors.EVENT_READ)
                    while sel.get_map():
                        if time.monotonic() - started >= timeout:
                            receipt["outcome"] = "timeout"
                            stop_group(proc)
                            break
                        for key, _ in sel.select(0.2):
                            chunk = os.read(key.fileobj.fileno(), 65536)
                            if not chunk:
                                sel.unregister(key.fileobj)
                                continue
                            remaining = max(0, LOG_LIMIT - written)
                            log.write(chunk[:remaining]); log.flush()
                            written += min(len(chunk), remaining)
                            if len(chunk) > remaining:
                                receipt["log_truncated"] = True
                if receipt["outcome"] != "timeout":
                    remaining = max(0.01, timeout - (time.monotonic() - started))
                    try:
                        proc.wait(timeout=remaining)
                        receipt["outcome"] = "exited"
                    except subprocess.TimeoutExpired:
                        receipt["outcome"] = "timeout"
                        stop_group(proc)
                receipt["exit_code"] = proc.returncode
        except KeyboardInterrupt:
            if proc:
                stop_group(proc)
            receipt["outcome"] = "interrupted"
        except OSError as e:
            receipt["outcome"] = "launch_error"
            receipt["error"] = str(e)
        finally:
            if proc and proc.poll() is None:
                stop_group(proc)
            if proc and proc.stdout:
                proc.stdout.close()
            receipt["finished_at"] = now()
            receipt["duration_seconds"] = round(time.monotonic() - started, 3)
            try:
                receipt["after"] = stable_snapshot(repo)
            except (ValueError, OSError, subprocess.SubprocessError) as e:
                receipt["snapshot_error"] = str(e)
            receipt["log_digest"] = digest(logfile.read_bytes()) if logfile.exists() else None
            write_json(folder / (run_id + ".receipt.json"), receipt)
        return receipt


def freshness(receipt, current):
    before, after = receipt.get("before"), receipt.get("after")
    if not before or not after:
        return "unknown"
    if before["digest"] != after["digest"]:
        return "changed-during-check"
    return "same-snapshot" if after["digest"] == current["digest"] else "stale"


def safe_text(text):
    return "".join(c if c in "\n\t" or (c.isprintable() and ord(c) != 127) else "?" for c in str(text))


def fenced(text):
    text = safe_text(text)
    # Longer than any embedded run, including backticks adjacent to other text.
    import re
    fence = "`" * max(3, max((len(x) for x in re.findall(r"`+", text)), default=0) + 1)
    return fence + "\n" + text + "\n" + fence


def report(repo, store):
    folder = task_dir(store)
    task = json.loads((folder / "task.json").read_text())
    current = stable_snapshot(repo)
    diff = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--")
    status = git(repo, "status", "--short", "--untracked-files=all").decode(errors="replace")
    if stable_snapshot(repo) != current:
        raise ValueError("Worktree changed while preparing packet; retry when idle.")
    lines = ["# Review Pack", "", f"Generated: {now()}", f"Repository: {json.dumps(str(repo))}",
             f"Task: {task['id']}", f"HEAD: {current['head']}",
             f"Snapshot: {current['digest']}", "", "## Task brief (explicit input)",
             fenced(task["brief"]), "", "## Scope",
             "Whole working tree against current HEAD: staged + unstaged; untracked paths listed below.",
             "Not a last-turn diff. Untracked contents are fingerprinted but are NOT included in diff.patch.",
             "Ignored files, environment, dependencies and remote services are outside the fingerprint.",
             "Snapshots are sampled, not a filesystem transaction; temporary changes between samples can be missed.",
             fenced(status or "Clean working tree"), "", "## Recorded checks"]
    receipts = []
    for p in sorted(folder.glob("*.receipt.json")):
        r = json.loads(p.read_text())
        if r.get("task_id") != task["id"] or r.get("brief_digest") != task["brief_digest"]:
            raise ValueError("Receipt belongs to a different task/brief: " + p.name)
        if r.get("log") != r.get("id", "") + ".log" or not isinstance(r.get("id"), str) or not all(c in "0123456789abcdef" for c in r["id"]) or len(r["id"]) != 32:
            raise ValueError("Invalid receipt log reference.")
        log = folder / r["log"]
        intact = log.exists() and digest(log.read_bytes()) == r.get("log_digest")
        r["freshness"] = freshness(r, current) if intact else "evidence-missing-or-modified"
        receipts.append(r)
    receipts.sort(key=lambda r: r["started_at"])
    if not receipts:
        lines.append("NOT PROVIDED — no command receipts recorded for this task.")
    for r in receipts:
        lines.extend(["", "### " + r["id"], fenced(shlex.join(r["argv"])),
                      f"Outcome: {r['outcome']}; exit code: {r['exit_code']}; snapshot relation: {r['freshness']}",
                      f"Started: {r['started_at']}; duration: {r['duration_seconds']}s",
                      f"Log: {json.dumps(str(folder / r['log']))}; truncated: {r['log_truncated']}"])
    lines.extend(["", "## Human decision", "Not assessed. Exit 0 records command completion, not test coverage or acceptance.",
                  "Inspect the requirement, diff and logs before accepting or requesting changes."])
    # Each export is immutable and separate from the reviewed repository.
    exported = folder / ("packet-" + uuid.uuid4().hex)
    exported.mkdir(mode=0o700)
    (exported / "review.md").write_text("\n".join(lines) + "\n")
    (exported / "diff.patch").write_bytes(diff)
    write_json(exported / "packet.json", {"schema_version": 1, "task": task, "snapshot": current,
                                          "receipts": receipts, "generated_at": now()})
    return exported


def open_panel():
    if os.environ.get("HERDR_ENV") != "1":
        raise ValueError("Invoke this action inside Herdr; standalone CLI commands need no Herdr session.")
    ctx = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON", "{}"))
    cwd = ctx.get("focused_pane_cwd") or ctx.get("workspace_cwd")
    pane_id = ctx.get("focused_pane_id")
    if pane_id:
        response = subprocess.run([os.environ.get("HERDR_BIN_PATH", "herdr"), "pane", "list"],
                                  capture_output=True, text=True, check=True, timeout=15)
        panes = json.loads(response.stdout)["result"]["panes"]
        matching = [p for p in panes if p.get("pane_id") == pane_id]
        if len(matching) != 1:
            raise ValueError("Invocation pane is no longer available; invoke again.")
        cwd = matching[0].get("foreground_cwd") or cwd
    if not cwd:
        raise ValueError("No invocation directory. Open the pane with an explicit --cwd.")
    repo = root(cwd)
    subprocess.run([os.environ.get("HERDR_BIN_PATH", "herdr"), "plugin", "pane", "open",
                    "--plugin", "herdr-review-pack", "--entrypoint", "review", "--cwd", str(repo)],
                   check=True, timeout=15)


def view(text):
    text = safe_text(text)
    if sys.stdout.isatty():
        try:
            subprocess.run(["less"], input=text.encode(), env={**os.environ, "LESS": "-S", "LESSOPEN": "", "LESSCLOSE": ""}, check=False)
            return
        except FileNotFoundError:
            pass
    print(text)


def panel(repo, store):
    while True:
        print(f"\nReview Pack {VERSION} — {safe_text(repo)}")
        print("Shared state directory (--state-dir): " + safe_text(store.parent))
        print("[b] Begin task from brief file  [r] Review packet  [d] Diff  [l] Check log  [q] Quit")
        try:
            choice = input("> ").strip().lower()
            if choice in ("q", ""):
                return
            if choice == "b":
                brief = input("Brief file path (starts a new task; prior receipts stay archived): ")
                print(begin(repo, store, brief))
            elif choice in ("r", "d", "l"):
                packet = report(repo, store)
                print("Packet saved: " + str(packet))
                if choice == "l":
                    data = json.loads((packet / "packet.json").read_text())
                    for i, r in enumerate(data["receipts"], 1):
                        print(i, safe_text(shlex.join(r["argv"])), r["freshness"])
                    if not data["receipts"]:
                        continue
                    selected = int(input("Log number: ")) - 1
                    if not 0 <= selected < len(data["receipts"]):
                        raise ValueError("Invalid log number")
                    p = packet.parent / data["receipts"][selected]["log"]
                else:
                    p = packet / ("review.md" if choice == "r" else "diff.patch")
                view(p.read_text(errors="replace"))
        except EOFError:
            return
        except (ValueError, KeyError, OSError, subprocess.SubprocessError) as e:
            print("Error: " + safe_text(e), file=sys.stderr)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", default=".")
    p.add_argument("--state-dir")
    sub = p.add_subparsers(dest="action", required=True)
    b = sub.add_parser("begin", help="Start a task from an explicit Markdown brief")
    b.add_argument("--brief", required=True)
    c = sub.add_parser("check", help="Record an explicitly requested command")
    c.add_argument("--timeout", type=float, default=120)
    c.add_argument("command", nargs=argparse.REMAINDER)
    sub.add_parser("pack", help="Export an immutable review packet")
    sub.add_parser("panel", help="Interactive review pane")
    sub.add_parser("open", help="Herdr action: open the review pane")
    args = p.parse_args(argv)
    try:
        if args.action == "open":
            open_panel(); return 0
        repo = root(args.repo)
        store = store_for(repo, state_base(args.state_dir))
        if args.action == "begin":
            print(begin(repo, store, args.brief))
        elif args.action == "check":
            import math
            if not math.isfinite(args.timeout) or args.timeout <= 0:
                raise ValueError("Timeout must be a finite positive number.")
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            r = run_check(repo, store, command, args.timeout)
            # One human/agent-readable line on stdout; the full receipt on stderr so a
            # calling agent does not mistake the JSON dump for the command's own output.
            print(f"review-pack receipt {r['id']}: outcome={r['outcome']} exit_code={r['exit_code']} "
                  f"duration={r['duration_seconds']}s log={store / r['task_id'] / r['log']}")
            print(json.dumps(r, indent=2), file=sys.stderr)
            return (r["exit_code"] if r["exit_code"] is not None and 0 <= r["exit_code"] <= 255 else 1) if r["outcome"] == "exited" else 1
        elif args.action == "pack":
            print(report(repo, store))
        elif args.action == "panel":
            panel(repo, store)
        return 0
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as e:
        print("Review Pack: " + safe_text(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
