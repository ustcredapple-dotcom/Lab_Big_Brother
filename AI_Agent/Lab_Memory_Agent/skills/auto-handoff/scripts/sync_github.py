from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


REMOTE = "origin"
BRANCH = "main"
MAX_PUBLIC_FILE_BYTES = 10 * 1024 * 1024
ALLOWED_PRIVATE_TREE_EXCEPTIONS = {
    "AI_Agent/Lab_Memory_Agent/config/onenote_sync.example.json",
    "AI_Agent/Lab_Memory_Agent/entries/2026-06-11-auto-work-handoff.md",
    "AI_Agent/Lab_Memory_Agent/entries/2026-06-11-example.md",
    "AI_Agent/Lab_Memory_Agent/inbox/README.md",
    "AI_Agent/Lab_Memory_Agent/sources/example-source.md",
}
DENIED_EXACT = {
    "PROJECT_HANDOFF.md",
}
DENIED_PREFIXES = (
    "Document/",
    "AI_Agent/Lab_Memory_Agent/indices/",
    "AI_Agent/Lab_Memory_Agent/logs/",
)
CONTROLLED_PREFIXES = (
    "AI_Agent/Lab_Memory_Agent/config/",
    "AI_Agent/Lab_Memory_Agent/entries/",
    "AI_Agent/Lab_Memory_Agent/inbox/",
    "AI_Agent/Lab_Memory_Agent/sources/",
)
SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(
        r"(?i)(?:password|client[_-]?secret|access[_-]?token|refresh[_-]?token|api[_-]?key)"
        r"\s*[:=]\s*['\"][^'\"]{8,}['\"]"
    ),
)


def default_root() -> Path:
    return Path(__file__).resolve().parents[5]


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def staged_paths(root: Path) -> list[str]:
    result = git(root, "diff", "--cached", "--name-only")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_denied(path: str) -> bool:
    if path in DENIED_EXACT:
        return True
    if path.startswith(DENIED_PREFIXES):
        return True
    if path.startswith(CONTROLLED_PREFIXES) and path not in ALLOWED_PRIVATE_TREE_EXCEPTIONS:
        return True
    lowered = path.lower()
    return any(part in lowered for part in ("token_cache", ".onepkg", ".onetoc2"))


def staged_blob(root: Path, path: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), "show", f":{path}"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def validate_staged(root: Path, paths: list[str]) -> None:
    problems = []
    for path in paths:
        if is_denied(path):
            problems.append(f"private path: {path}")
            continue
        if not (root / path).exists():
            continue
        content = staged_blob(root, path)
        if len(content) > MAX_PUBLIC_FILE_BYTES:
            problems.append(f"file exceeds 10 MiB public limit: {path}")
            continue
        if b"\x00" in content[:8192]:
            continue
        text = content.decode("utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            problems.append(f"possible embedded credential: {path}")
    if problems:
        details = "\n".join(f"- {problem}" for problem in problems)
        raise RuntimeError(f"GitHub sync blocked by public-repository safety checks:\n{details}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Commit and push the public-safe portion of the ZZLab AI project."
    )
    parser.add_argument("--root", help="Override the shared ZZLab_AI root")
    parser.add_argument("--message", help="Commit message")
    parser.add_argument("--no-push", action="store_true", help="Commit locally without pushing")
    parser.add_argument("--dry-run", action="store_true", help="Show public changes without committing")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve() if args.root else default_root()
    if not (root / ".git").exists():
        raise SystemExit(f"not a Git repository: {root}")

    git(root, "add", "-A")
    paths = staged_paths(root)
    if not paths:
        print("GitHub sync: no public changes to commit")
        return
    for path in paths:
        if (root / path).is_file():
            git(root, "update-index", "--chmod=-x", "--", path)
    validate_staged(root, paths)

    print("Public changes:")
    for path in paths:
        print(f"- {path}")
    if args.dry_run:
        git(root, "reset", check=True)
        return

    message = args.message or f"chore: sync project {datetime.now().astimezone():%Y-%m-%d %H:%M %z}"
    commit = git(root, "commit", "-m", message, check=False)
    if commit.stdout:
        print(commit.stdout.rstrip())
    if commit.returncode:
        raise SystemExit(commit.returncode)

    if args.no_push:
        print("GitHub sync: local commit created; push skipped")
        return

    push = git(root, "push", "-u", REMOTE, BRANCH, check=False)
    if push.stdout:
        print(push.stdout.rstrip())
    if push.returncode:
        print("GitHub sync: push failed; the commit remains local", file=sys.stderr)
        raise SystemExit(push.returncode)
    print("GitHub sync: pushed origin/main")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
