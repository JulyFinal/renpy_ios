#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
box_project.py —— 组装 RenPyBox（"一个 ipa 装多个游戏"的通用引擎）项目目录

产出的项目目录结构（喂给 `renpy launcher ios_create`）：

    <out>/
        game/
            zz_box_picker.rpy      # 开局选择器（repo 里 box/game/zz_box_picker.rpy）
            zz_ios_patch.rpy       # 显示/GUI 修正（repo 里 scripts/zz_ios_patch.rpy）
            zz_ios_build.rpy       # 本脚本生成的最小构建配置
            script_version.txt     # 占位，避免 launcher 报版本缺失
            fonts/SourceHanSansLite.ttf   # 2.9MB 中文字体（Ren'Py 默认字体没有中文）

注意：这里**不放任何游戏**。游戏在 iPad 上以
`<Documents>/games/<slug>/game/` 的形式存在，由 base/main.py 改过的
predefined_searchpath() 决定这次启动加载哪一个。

用法：
    python3 scripts/box_project.py --repo /path/to/renpy_ios --sdk /path/to/renpy-V-sdk \
        --out /path/work/RenPyBox
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

FONT_REL = "sdk-fonts/SourceHanSansLite.ttf"

BUILD_RPY = '''\
# 本文件由 scripts/box_project.py 生成，请不要手改。

init -1600 python:
    # 存档目录由 base/main.py 的 path_to_saves() 接管（按游戏 slug 分开），
    # 这里的值只是占位；iOS 上原本就会忽略它。
    config.save_directory = "RenPyOSBox"

init -1400 python:
    # 注意：这里必须用默认 store 的 python 块。
    # `python in build:` 里 globals 就是 build store 自己，名字 `build` 不存在，
    # 会 NameError；而在默认 store 里 `build` 是能拿到的模块对象。
    build.name = "RenPyOSBox"
    build.directory_name = "RenPyOSBox-1.0"

    # 只把 .rpyc 放进包里，源码 .rpy 不要（省体积，也避免被反编译）。
    build.classify("game/**.rpy", None)
    build.classify("game/**.rpym", None)
    build.classify("game/**.ttf", "all")
    build.classify("game/**.otf", "all")

init 999 python:
    config.name = "RenPyOSBox"
    config.version = "1.0.0"
'''


def log(msg: str) -> None:
    print(f"[box_project] {msg}")


def find_font(sdk: Path) -> Path:
    p = sdk / FONT_REL
    if p.is_file():
        return p
    # 兼容：有的 SDK 版本把字体放在 launcher/game/fonts/
    for cand in sdk.rglob("SourceHanSansLite.ttf"):
        return cand
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description="assemble the RenPyBox project")
    ap.add_argument("--repo", required=True, help="path to the renpy_ios repo checkout")
    ap.add_argument("--sdk", required=True, help="path to the Ren'Py SDK (for the CJK font)")
    ap.add_argument("--out", required=True, help="output project directory")
    ap.add_argument("--clean", action="store_true", help="delete --out first")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    sdk = Path(args.sdk).resolve()
    out = Path(args.out).resolve()

    picker_src = repo / "box" / "game" / "zz_box_picker.rpy"
    patch_src = repo / "scripts" / "zz_ios_patch.rpy"

    for p in (picker_src, patch_src):
        if not p.is_file():
            log(f"ERROR: missing {p}")
            return 1

    font = find_font(sdk)
    if not font.is_file():
        log(f"ERROR: can't find {FONT_REL} under {sdk}")
        return 1

    if args.clean and out.exists():
        log(f"removing {out}")
        shutil.rmtree(out)

    gamedir = out / "game"
    (gamedir / "fonts").mkdir(parents=True, exist_ok=True)

    shutil.copy2(picker_src, gamedir / "zz_box_picker.rpy")
    shutil.copy2(patch_src, gamedir / "zz_ios_patch.rpy")
    shutil.copy2(font, gamedir / "fonts" / "SourceHanSansLite.ttf")

    (gamedir / "zz_ios_build.rpy").write_text(BUILD_RPY, encoding="utf-8")

    # launcher / ios_create 会去读 script_version.txt 做兼容性提示，给个占位。
    (gamedir / "script_version.txt").write_text("(7, 7, 3)\n", encoding="utf-8")

    log(f"project: {out}")
    for p in sorted(gamedir.rglob("*")):
        if p.is_file():
            log(f"  game/{p.relative_to(gamedir)}  ({p.stat().st_size} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())