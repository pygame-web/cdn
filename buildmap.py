#!/bin/env python3
import json
from pathlib import Path
from zipfile import ZipFile


MAP = {"-CDN-": "https://pygame-web.github.io/cdn/"}


# https://pypi.org/simple/pygbag/?format=application/vnd.pypi.simple.latest+json

# top_level.txt fallback from pyodide ( for ref)
# https://github.com/pyodide/pyodide/blob/90e20badd76d8a8b911f77034512137cc2e7d585/pyodide-build/pyodide_build/common.py#L123-L133
# https://github.com/pypa/setuptools/blob/d680efc8b4cd9aa388d07d3e298b870d26e9e04b/setuptools/discovery.py#L122

# top_level fallback from pradyunsg used there
# https://gist.github.com/pradyunsg/22ca089b48ca55d75ca843a5946b2691

from collections import deque
from typing import Iterable
from installer.sources import WheelFile, WheelSource
from installer.utils import parse_metadata_file


def _find_importable_components_from_wheel_content_listing(
    filepaths: Iterable[str], *, dist_info_dir: str, data_dir: str
) -> Iterable[tuple[str, ...]]:
    purelib_str = f"{data_dir}/purelib/"
    platlib_str = f"{data_dir}/platlib/"
    for path in filepaths:
        if path.startswith(dist_info_dir):
            # Nothing in dist-info is importable.
            continue

        if path.startswith((platlib_str, purelib_str)):
            # Remove the prefix from purelib and platlib files.
            name = path[len(platlib_str) :]
        elif path.startswith(data_dir):
            # Nothing else in data is importable.
            continue
        else:
            # Top level files end up in an importable location.
            name = path

        if name.endswith(".py"):
            yield tuple(name[: -len(".py")].split("/"))


def find_major_import_import_names(wheel: WheelSource) -> Iterable[str]:
    metadata = parse_metadata_file(wheel.read_dist_info("WHEEL"))
    if not (metadata["Wheel-Version"] and metadata["Wheel-Version"].startswith("1.")):
        raise NotImplementedError("Only supports wheel 1.x")

    filepaths: Iterable[str] = (record_elements[0] for record_elements, _, _ in wheel.get_contents())
    importable_components = _find_importable_components_from_wheel_content_listing(
        filepaths, dist_info_dir=wheel.dist_info_dir, data_dir=wheel.data_dir
    )

    return _determine_major_import_names(importable_components)


def _determine_major_import_names(importable_components: Iterable[tuple[str, ...]]) -> Iterable[str]:
    # If you literally want the "top level", just do...
    # return {components[0] for components in importable_components}

    # Here, we're going to try to find the longest initial import name instead.
    # Mostly, because this was a fun problem to thing through.

    # Build a tree out of the components
    tree = {}
    for components in importable_components:
        subtree = tree
        for segment in components:
            if segment not in subtree:
                subtree[segment] = {}
            subtree = subtree[segment]

    # Recurse through the tree to find the names which have != 1 children.
    queue = deque()
    queue.appendleft((tree, ()))
    while queue:
        current_tree, current_name = queue.popleft()

        for name, subtree in current_tree.items():
            subname = (*current_name, name)
            if len(subtree) == 1:
                queue.append((subtree, subname))
            elif name == "__init__":
                yield ".".join(current_name)
            else:
                yield ".".join(subname)


def process_wheel(whl, whlname):
    found = False
    tln = ""
    with ZipFile(whl) as archive:
        for name in archive.namelist():
            if name.endswith(".dist-info/top_level.txt"):
                f = archive.open(name)
                for btln in f.readlines(): # f.read().decode().split("\n"):
                    tln = btln.decode().strip().replace("/", ".")
                    if not tln:
                        continue

                    # pyodide's kiwisolver has src in dist-info toplevel
                    if tln == "src":
                        continue

                    # =============================================================================
                    if tln == "cwcwidth":
                        print(f"forced: {whlname} -> wcwidth")
                        MAP["wcwidth"] = whlname

                    if tln == "pygame.base":
                        print(f"forced: {whlname} -> pygame")
                        MAP["pygame"] = whlname

                    # =============================================================================
                    if tln in MAP:
                        print(f"override pkg name toplevel {tln} with", whlname)
                    MAP[tln] = whlname

                if tln:
                    archive.close()
                    found = True
                    break

        if not found:
            print()
            print("MISSING TOPLEVEL :", whl)
            wheel_file = WheelFile(archive)
            for tln in find_major_import_import_names(wheel_file):
                MAP[tln] = whlname
                print("\tguessed :", tln)
                found = True
                archive.close()
                break

    if found:
        return tln
    return ""

import pygbag



print(
    f"""

        ============== {pygbag.VERSION = } pure/abi3 ======================


"""
)


# process pure wheels and abi3

for repo in ["pkg/*.whl",]: #f"{pygbag.VERSION}/*.whl"]:
    for whl in Path(".").glob(repo):
        whlname = whl.as_posix()
        found = process_wheel(whl, whlname)
        if not found:
            print(f"Toplevel not found in {whl} !" )


for repo in ["abi3/*.whl",]: # f"{pygbag.VERSION}/*.whl"]:
    for whl in Path(".").glob(repo):
        whlname = whl.as_posix()
        abi3 = False
        # keep only abi3
        if str(whl).find("-wasm32") > 0:
            if str(whl).find("-abi3-") < 0:
                continue
            else:
                abi3 = True

        if not abi3:
            for replace in ("-cp310", "-cp311", "-cp312", "-cp313", "-cp314"):
                whlname = whlname.replace(replace, "-<abi>")

        found = process_wheel(whl, whlname)
        if not found:
            print(f"Toplevel not found in {whl} !" )



print(
    f"""


        ============== {pygbag.VERSION = } c-api bi ======================



"""
)

UNIVERSAL = MAP.copy()

# get cpython versions
for abi_folder in Path(f".").glob("cp3??"):
    print(abi_folder)

    MAP = UNIVERSAL.copy()

    # grab only python-wasm-sdk wheels and pyodide generated one -emscripten_3_M_mm_wasm32.whl
    # for matching version

    for repo in [f"{abi_folder}/*wasm32*.whl", f"{abi_folder}-{pygbag.VERSION}/*wasm32*.whl"]:
        print(f"""
   ======= Scanning {repo} =====
        """)
        for whl in Path(".").glob(repo):
            whlname = whl.as_posix()

            if whlname.find("-abi3-") > 0:
                print("WARNING: abi3 ?", whlname )
            else:
                # 0.9 drop 3.10 & 3.11
                if whlname.find("-cp310") > 0:
                    continue

                if whlname.find("-cp311") > 0:
                    continue

                for replace in ("-cp310", "-cp311", "-cp312", "-cp313", "-cp314"):
                    whlname = whlname.replace(replace, "-<abi>")

                print(f"""\t\tfound : {whlname}""")

            whlname = whlname.replace("-wasm32_bi_emscripten", "-<api>")

            process_wheel(whl, whlname)

    # input()

    for py in Path(".").glob("vendor/*.py"):
        tln = py.stem
        MAP[tln] = py.as_posix()

    for k, v in MAP.items():
        print(k, v)

    with open(f"index-{pygbag.VERSION}-{abi_folder}.json", "w") as f:
#    with open(f"{pygbag.VERSION}/{abi_folder}.json", "w") as f:
        print(json.dumps(MAP, sort_keys=True, indent=4), file=f)
