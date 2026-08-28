#!/usr/bin/env python3

import argparse
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


SYNC_PATHS = (
    "CommonModules/КОД_ДиспетчерРегистрацииКОбмену.xml",
    "CommonModules/КОД_ДиспетчерРегистрацииКОбмену",
    "CommonPictures/КОД_КонвейерОбменаДанными.xml",
    "CommonPictures/КОД_КонвейерОбменаДанными",
    "DataProcessors/КОД_КонвейерОбработчиковБазовый.xml",
    "DataProcessors/КОД_КонвейерОбработчиковБазовый",
    "DataProcessors/КОД_РеестрСценариев_ИмяПланаОбмена.xml",
    "DataProcessors/КОД_РеестрСценариев_ИмяПланаОбмена",
    "DataProcessors/КОД_РучнаяРегистрация.xml",
    "DataProcessors/КОД_РучнаяРегистрация",
    "Languages/Русский.xml",
)

METADATA_PREFIXES = (
    "CommonModule.КОД_ДиспетчерРегистрацииКОбмену",
    "CommonPicture.КОД_КонвейерОбменаДанными",
    "DataProcessor.КОД_КонвейерОбработчиковБазовый",
    "DataProcessor.КОД_РеестрСценариев_ИмяПланаОбмена",
    "DataProcessor.КОД_РучнаяРегистрация",
    "Language.Русский",
)


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--core", required=True, type=Path)
    parser.add_argument("--demo", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    return parser.parse_args()


def is_linked_metadata(name):
    return any(name == prefix or name.startswith(prefix + ".") for prefix in METADATA_PREFIXES)


def ensure_inside(path, root):
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
    except ValueError as error:
        raise RuntimeError(f"Path is outside repository: {path}") from error


def git_status(repository, relative_path):
    result = subprocess.run(
        [
            "git",
            "-C",
            os.fspath(repository),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            os.fspath(relative_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout


def same_file(source, destination):
    return destination.is_file() and source.read_bytes() == destination.read_bytes()


def directory_snapshot(path):
    if not path.is_dir():
        return None

    result = {}
    for item in path.rglob("*"):
        relative_path = item.relative_to(path).as_posix()
        if item.is_symlink():
            result[relative_path] = ("link", os.readlink(item))
        elif item.is_dir():
            result[relative_path] = ("directory", None)
        elif item.is_file():
            result[relative_path] = ("file", item.read_bytes())
        else:
            result[relative_path] = ("other", None)
    return result


def same_path(source, destination):
    if source.is_file():
        return same_file(source, destination)
    if source.is_dir():
        return directory_snapshot(source) == directory_snapshot(destination)
    return False


def validate_sync_paths(core_source, demo_source, demo_repository):
    conflicts = []
    for relative_path_text in SYNC_PATHS:
        relative_path = Path(relative_path_text)
        source = core_source / relative_path
        destination = demo_source / relative_path
        ensure_inside(source, core_source)
        ensure_inside(destination, demo_source)

        if not source.exists():
            raise RuntimeError(f"Core path does not exist: {source}")

        demo_relative_path = Path("src") / relative_path
        if git_status(demo_repository, demo_relative_path) and not same_path(source, destination):
            conflicts.append(os.fspath(demo_relative_path))

    if conflicts:
        formatted_paths = "\n".join(f"  {path}" for path in conflicts)
        raise RuntimeError(
            "Synchronization would overwrite local changes in linked paths:\n"
            f"{formatted_paths}\n"
            "Commit or stash them before synchronization."
        )


def replace_path(source, destination):
    if destination.is_symlink() or destination.is_file():
        destination.unlink()
    elif destination.is_dir():
        shutil.rmtree(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination)


def metadata_versions(xml_content, description):
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as error:
        raise RuntimeError(f"Invalid {description}: {error}") from error

    result = {}
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "Metadata":
            continue
        name = element.attrib.get("name")
        if name and is_linked_metadata(name):
            result[name] = (
                element.attrib.get("id"),
                element.attrib.get("configVersion"),
            )
    return result


def head_config_dump(demo_repository):
    result = subprocess.run(
        ["git", "-C", os.fspath(demo_repository), "show", "HEAD:src/ConfigDumpInfo.xml"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def validate_metadata(core_metadata, demo_metadata, head_metadata):
    if set(core_metadata) != set(demo_metadata):
        missing = sorted(set(core_metadata) - set(demo_metadata))
        extra = sorted(set(demo_metadata) - set(core_metadata))
        details = []
        if missing:
            details.append("missing in demo: " + ", ".join(missing))
        if extra:
            details.append("missing in core: " + ", ".join(extra))
        raise RuntimeError(
            "Linked ConfigDumpInfo.xml structure differs ("
            + "; ".join(details)
            + "). Export the demo configuration and reconcile the structure manually."
        )

    for name, (core_id, core_version) in core_metadata.items():
        demo_id, demo_version = demo_metadata[name]
        if core_id != demo_id:
            raise RuntimeError(f"Metadata UUID differs for {name}: core={core_id}, demo={demo_id}")
        if core_version is None or demo_version is None:
            raise RuntimeError(f"configVersion is missing for linked metadata: {name}")

        head_value = head_metadata.get(name)
        if head_value is None:
            raise RuntimeError(f"Linked metadata is missing in demo HEAD: {name}")
        head_id, head_version = head_value
        if head_id != demo_id:
            raise RuntimeError(f"Metadata UUID differs from demo HEAD for {name}")
        if demo_version not in (head_version, core_version):
            raise RuntimeError(
                f"Local configVersion was changed for {name}. "
                "Commit or stash that change before synchronization."
            )


def replace_config_versions(demo_content, core_metadata):
    has_bom = demo_content.startswith(b"\xef\xbb\xbf")
    text = demo_content.decode("utf-8-sig")

    for name, (_, version) in sorted(core_metadata.items()):
        tag_pattern = re.compile(
            r'<Metadata\b(?=[^>]*\bname="' + re.escape(name) + r'")[^>]*>'
        )
        matches = list(tag_pattern.finditer(text))
        if len(matches) != 1:
            raise RuntimeError(f"Expected one ConfigDumpInfo.xml entry for {name}, found {len(matches)}")

        match = matches[0]
        tag = match.group(0)
        updated_tag, replacements = re.subn(
            r'(\bconfigVersion=")[^"]*(")',
            lambda version_match: version_match.group(1) + version + version_match.group(2),
            tag,
            count=1,
        )
        if replacements != 1:
            raise RuntimeError(f"configVersion attribute not found for {name}")
        text = text[: match.start()] + updated_tag + text[match.end() :]

    encoded = text.encode("utf-8")
    return (b"\xef\xbb\xbf" + encoded) if has_bom else encoded


def synchronize(args):
    core_repository = args.core.resolve(strict=True)
    demo_repository = args.demo.resolve(strict=True)
    core_source = core_repository / "src"
    demo_source = demo_repository / "src"

    ensure_inside(core_source, core_repository)
    ensure_inside(demo_source, demo_repository)
    validate_sync_paths(core_source, demo_source, demo_repository)

    core_dump_path = core_source / "ConfigDumpInfo.xml"
    demo_dump_path = demo_source / "ConfigDumpInfo.xml"
    core_metadata = metadata_versions(core_dump_path.read_bytes(), "core ConfigDumpInfo.xml")
    demo_content = demo_dump_path.read_bytes()
    demo_metadata = metadata_versions(demo_content, "demo ConfigDumpInfo.xml")
    head_metadata = metadata_versions(head_config_dump(demo_repository), "demo HEAD ConfigDumpInfo.xml")
    validate_metadata(core_metadata, demo_metadata, head_metadata)

    for relative_path_text in SYNC_PATHS:
        relative_path = Path(relative_path_text)
        replace_path(core_source / relative_path, demo_source / relative_path)

    updated_dump = replace_config_versions(demo_content, core_metadata)
    if updated_dump != demo_content:
        demo_dump_path.write_bytes(updated_dump)

    (demo_repository / "CORE_VERSION").write_text(args.commit + "\n", encoding="ascii")


def main():
    try:
        synchronize(parse_arguments())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"sync-core: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
