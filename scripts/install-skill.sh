#!/usr/bin/env bash
# Install (or update) the collect-only `figure-collect` skill for Claude Code and Codex.
# Copies skills/figure-collect into ~/.claude/skills and ~/.codex/skills. Re-run after editing.
set -euo pipefail
src="$(cd "$(dirname "$0")/.." && pwd)/skills/figure-collect"
test -f "$src/SKILL.md" || { echo "缺少 $src/SKILL.md" >&2; exit 1; }
for base in "$HOME/.claude/skills" "$HOME/.codex/skills"; do
  dest="$base/figure-collect"
  mkdir -p "$base"
  if [ -L "$dest" ]; then
    echo "跳过 $dest：已是符号链接，请手动确认" >&2
    continue
  fi
  rm -rf "$dest"
  cp -R "$src" "$dest"
  echo "已安装：$dest"
done
