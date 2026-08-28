#!/usr/bin/env sh

set -eu

core_remote_name="upstream"
core_remote_url="https://github.com/i-simonov/1c-exchange-pipeline.git"
repository_root=$(git rev-parse --show-toplevel)

if git -C "$repository_root" remote get-url "$core_remote_name" >/dev/null 2>&1; then
	current_remote_url=$(git -C "$repository_root" remote get-url "$core_remote_name")
	if [ "$current_remote_url" != "$core_remote_url" ]; then
		echo "Remote '$core_remote_name' already points to '$current_remote_url'." >&2
		exit 1
	fi
else
	git -C "$repository_root" remote add "$core_remote_name" "$core_remote_url"
fi

git -C "$repository_root" config merge.keep-demo.name "Keep demo-owned overridable modules"
git -C "$repository_root" config merge.keep-demo.driver true
