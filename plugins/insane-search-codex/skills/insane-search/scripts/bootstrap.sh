#!/usr/bin/env bash
set -euo pipefail

INSTALL=false
if [[ "${1:-}" == "--install" ]]; then
  INSTALL=true
fi

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE_DIR="$SKILL_DIR/engine/templates"
NODE_DEPS_DIR="${INSANE_NODE_DEPS_DIR:-$HOME/.insane-search/node}"

python_check() {
  local module="$1"
  python3 - <<PY >/dev/null 2>&1
import importlib
importlib.import_module("$module")
PY
}

need_python=()
for spec in "curl_cffi:curl_cffi>=0.15.0" "bs4:beautifulsoup4" "yaml:pyyaml" "pypdf:pypdf" "markdownify:markdownify"; do
  module="${spec%%:*}"
  package="${spec##*:}"
  if ! python_check "$module"; then
    need_python+=("$package")
  fi
done

need_node=false
if ! command -v node >/dev/null 2>&1; then
  need_node=true
elif ! command -v npm >/dev/null 2>&1; then
  need_node=true
fi

if [[ ${#need_python[@]} -eq 0 && "$need_node" == false ]]; then
  echo "bootstrap: Python and Node prerequisites look available"
  exit 0
fi

echo "bootstrap: missing prerequisites detected"
if [[ ${#need_python[@]} -gt 0 ]]; then
  echo "  python packages: ${need_python[*]}"
fi
if [[ "$need_node" == true ]]; then
  echo "  node or npm is missing"
fi

if [[ "$INSTALL" != true ]]; then
  echo "bootstrap: rerun with --install to install missing Python packages and Node dependencies"
  exit 1
fi

if [[ ${#need_python[@]} -gt 0 ]]; then
  python3 -m pip install --user -U "${need_python[@]}"
fi

if [[ "$need_node" == false ]]; then
  # Same location the engine uses for its own first-run install (reused across plugin versions,
  # injected via NODE_PATH). System Chrome is used via channel:'chrome', so skip the bundled browser.
  mkdir -p "$NODE_DEPS_DIR"
  cp "$TEMPLATE_DIR/package.json" "$NODE_DEPS_DIR/"
  (cd "$NODE_DEPS_DIR" && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install)
fi

echo "bootstrap: install step completed"
