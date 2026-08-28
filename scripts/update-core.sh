#!/usr/bin/env sh

set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_root=$(git -C "$script_directory" rev-parse --show-toplevel)

"$script_directory/configure-core-dependency.sh"
git -C "$repository_root" fetch upstream main
git -C "$repository_root" merge --no-ff upstream/main
