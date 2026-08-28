#!/usr/bin/env sh

set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
demo_repository=$(git -C "$script_directory" rev-parse --show-toplevel)

if [ "$#" -gt 1 ]; then
	echo "Usage: $0 [path-to-core-repository]" >&2
	exit 2
fi

core_repository=${1:-${PIPELINE_CORE_REPOSITORY:-"$demo_repository/../1c-exchange-pipeline"}}

if [ ! -d "$core_repository" ]; then
	echo "Core repository not found: $core_repository" >&2
	exit 1
fi

core_repository=$(git -C "$core_repository" rev-parse --show-toplevel 2>/dev/null) || {
	echo "Not a Git repository: $core_repository" >&2
	exit 1
}

if [ "$core_repository" = "$demo_repository" ]; then
	echo "Core and demo repositories must be different." >&2
	exit 1
fi

if [ -n "$(git -C "$core_repository" status --porcelain)" ]; then
	echo "Core repository has uncommitted changes: $core_repository" >&2
	echo "Commit or stash them before synchronization." >&2
	exit 1
fi

core_commit=$(git -C "$core_repository" rev-parse HEAD)

python3 "$script_directory/sync_core.py" \
	--core "$core_repository" \
	--demo "$demo_repository" \
	--commit "$core_commit"

echo "Core synchronized from commit $core_commit."
echo "Review changes in the demo repository:"
git -C "$demo_repository" status --short
