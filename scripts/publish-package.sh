#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-.venv}"
PYTHON="$VENV_DIR/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing virtual environment. Run scripts/build-package.sh first." >&2
  exit 2
fi

if [[ "${REQUIRE_CLEAN_WORKTREE:-0}" == "1" && -n "$(git status --porcelain)" ]]; then
  echo "Refusing to publish from a dirty worktree because REQUIRE_CLEAN_WORKTREE=1." >&2
  git status --short >&2
  exit 2
fi

VERSION="$("$PYTHON" setup.py --version)"
TAG_NAME="${TAG_NAME:-$VERSION}"

if ! git rev-parse -q --verify "refs/tags/$TAG_NAME" >/dev/null; then
  echo "Missing release tag $TAG_NAME." >&2
  echo "Create and push the tag before publishing to PyPI." >&2
  exit 2
fi

if [[ "${SKIP_REMOTE_TAG_CHECK:-0}" != "1" ]]; then
  if ! git ls-remote --exit-code origin "refs/tags/$TAG_NAME" >/dev/null; then
    echo "Release tag $TAG_NAME is not available on origin." >&2
    echo "Push the tag first, or set SKIP_REMOTE_TAG_CHECK=1 only for offline validation." >&2
    exit 2
  fi
fi

TAG_COMMIT="$(git rev-list -n 1 "$TAG_NAME")"
HEAD_COMMIT="$(git rev-parse HEAD)"
if [[ "$TAG_COMMIT" != "$HEAD_COMMIT" ]]; then
  echo "Release tag $TAG_NAME does not point to HEAD; publishing existing dist artifacts." >&2
  echo "Tag commit: $TAG_COMMIT" >&2
  echo "HEAD commit: $HEAD_COMMIT" >&2
fi

if ! compgen -G "dist/*" >/dev/null; then
  echo "No distribution artifacts found. Run scripts/build-package.sh first." >&2
  exit 2
fi

DIST_FILES=()
while IFS= read -r dist_file; do
  DIST_FILES+=("$dist_file")
done < <(find dist -maxdepth 1 -type f \( -name "idelium-$VERSION.tar.gz" -o -name "idelium-$VERSION-*.whl" \) | sort)
if [[ "${#DIST_FILES[@]}" -eq 0 ]]; then
  echo "No distribution artifacts found for version $VERSION." >&2
  exit 2
fi

"$PYTHON" -m twine check "${DIST_FILES[@]}"

if [[ "${SKIP_PYPI_VERSION_CHECK:-0}" != "1" ]]; then
  if "$PYTHON" - "$VERSION" <<'PY'
import json
import sys
import urllib.error
import urllib.request

version = sys.argv[1]
url = "https://pypi.org/pypi/idelium/json"
try:
    with urllib.request.urlopen(url, timeout=15) as response:
        releases = json.load(response).get("releases", {})
except urllib.error.HTTPError as exc:
    print(f"Unable to check PyPI releases: HTTP {exc.code}", file=sys.stderr)
    sys.exit(2)
except Exception as exc:
    print(f"Unable to check PyPI releases: {exc}", file=sys.stderr)
    sys.exit(2)

if version in releases:
    print(f"Version {version} already exists on PyPI.", file=sys.stderr)
    sys.exit(1)
PY
  then
    :
  else
    check_status=$?
    if [[ "$check_status" -eq 1 ]]; then
      exit 2
    fi
    echo "Set SKIP_PYPI_VERSION_CHECK=1 only if you intentionally want to skip this network check." >&2
    exit 2
  fi
fi

REPOSITORY_ARGS=()
if [[ "${PYPI_REPOSITORY_URL:-}" != "" ]]; then
  REPOSITORY_ARGS+=(--repository-url "$PYPI_REPOSITORY_URL")
fi

echo "Publishing Idelium CLI $VERSION to PyPI."
echo "Use username __token__ and a project-scoped PyPI API token when prompted."
if [[ "${DRY_RUN:-0}" == "1" ]]; then
  printf 'Dry run enabled. Would upload:'
  printf ' %q' "${DIST_FILES[@]}"
  printf '\n'
  exit 0
fi
"$PYTHON" -m twine upload "${REPOSITORY_ARGS[@]}" "${DIST_FILES[@]}"
