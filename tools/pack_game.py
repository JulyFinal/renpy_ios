#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pack_game.py —— 把「仓库里的游戏源码」+「PC 版的大素材」拼成一个可以直接拷进
iPad 的 RenPyBox 游戏目录：

    <out>/<slug>/
        title.txt          # 选择器上显示的名字
        game/
            ... 脚本（.rpyc）+ 素材（images/ audio/ videos/ gui/ tl/ *.rpa ...）

放到 iPad 上的位置：`本应用/Documents/games/<slug>/`（整个 `<slug>` 文件夹拷进去）。

为什么分两个来源：
  * 仓库 `games/<Game>/game` 只放脚本/字体等小文件（源码进 git，素材不进）；
  * PC 版 `game/` 里有几个 GB 的图/音频/视频，但它们不进 git。

脚本类文件（.rpy/.rpyc/.rpym/.rpymc）**只从 --repo-game 取**，避免 PC 版里
unrpyc 反编译出来的残次 .rpy 混进来（MilfyCity 就是这样：.rpy 是坏的，
真正能跑的是 .rpyc）。

用法示例：

  # MilkyTouch：脚本来自仓库，素材来自 PC 版
  python tools/pack_game.py --slug milkytouch --title "MilkyTouch" \
      --repo-game games/MilkyTouch/game \
      --media "D:/games/MilkyTouch/MilkyTouch/game" \
      --out dist/games

  # MilfyCity 同理
  python tools/pack_game.py --slug milfyCity --title "Milfy City" \
      --repo-game games/MilfyCity/game \
      --media "D:/games/MilfyCity-1.0e-pc-compressed/game" \
      --out dist/games
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

# 这些扩展名只认 --repo-game 的版本
SCRIPT_EXT = {".rpy", ".rpyc", ".rpym", ".rpymc"}

# PC 版里绝对不要带过去的东西
SKIP_DIRS = {"saves", "cache", "__pycache__", ".git", ".svn", "cv2", "log.txt"}

# 机器相关/垃圾文件
SKIP_FILES = {"thumbs.db", "desktop.ini", ".ds_store", "traceback.txt", "errors.txt", "log.txt"}
SKIP_SUFFIX = ("~", ".bak", ".orig", ".pyc")


def log(msg: str) -> None:
    print(f"[pack_game] {msg}")


def human(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024.0 or unit == "GB":
            return f"{f:.1f} {unit}" if unit != "B" else f"{int(f)} B"
        f /= 1024.0
    return "?"


def should_skip_file(name: str) -> bool:
    low = name.lower()
    if low in SKIP_FILES:
        return True
    for suf in SKIP_SUFFIX:
        if low.endswith(suf):
            return True
    return False


def copy_tree(src: Path, dst: Path, skip_scripts: bool) -> tuple[int, int]:
    """把 src 复制到 dst；返回 (文件数, 字节数)。"""

    count = 0
    total = 0

    for dirpath, dirnames, filenames in os.walk(src):
        rel = Path(dirpath).relative_to(src)

        # 原地裁剪目录列表（os.walk 支持）
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]

        outdir = dst / rel
        outdir.mkdir(parents=True, exist_ok=True)

        for fn in filenames:
            if should_skip_file(fn):
                continue

            suffix = Path(fn).suffix.lower()

            if skip_scripts and suffix in SCRIPT_EXT:
                continue

            sp = Path(dirpath) / fn
            dp = outdir / fn

            try:
                if dp.exists() and dp.stat().st_size == sp.stat().st_size:
                    continue
            except OSError:
                pass

            shutil.copy2(sp, dp)
            count += 1
            total += dp.stat().st_size

    return count, total


def main() -> int:
    ap = argparse.ArgumentParser(description="assemble a RenPyBox game folder")
    ap.add_argument("--slug", required=True,
                    help="folder name under Documents/games/, e.g. milkytouch")
    ap.add_argument("--out", required=True, help="output root (will get <out>/<slug>/)")
    ap.add_argument("--repo-game", help="repo's games/<Game>/game (scripts; small)")
    ap.add_argument("--media", help="PC game's game/ dir (big media; may repeat)",
                    action="append", default=[])
    ap.add_argument("--title", help="display name in the picker (default: slug)")
    ap.add_argument("--clean", action="store_true", help="remove <out>/<slug> first")
    ap.add_argument("--list-only", action="store_true", help="only print the plan")
    args = ap.parse_args()

    if not args.repo_game and not args.media:
        log("ERROR: need at least one of --repo-game / --media")
        return 1

    out = Path(args.out).resolve()
    target = out / args.slug

    if args.clean and target.exists():
        log(f"removing {target}")
        shutil.rmtree(target)

    gamedir = target / "game"

    log(f"slug    : {args.slug}")
    log(f"target  : {target}")
    if args.repo_game:
        log(f"scripts : {args.repo_game}")
    for m in args.media:
        log(f"media   : {m}")

    if args.list_only:
        return 0

    gamedir.mkdir(parents=True, exist_ok=True)

    c1 = t1 = 0
    if args.repo_game:
        log("copying scripts/fonts/tl from repo ...")
        c1, t1 = copy_tree(Path(args.repo_game).resolve(), gamedir, skip_scripts=False)
        log(f"  -> {c1} files, {human(t1)}")

    c2 = t2 = 0
    for m in args.media:
        mpath = Path(m).resolve()
        if not mpath.is_dir():
            log(f"ERROR: media dir not found: {mpath}")
            return 1
        log(f"copying media from {mpath} ...")
        c, t = copy_tree(mpath, gamedir, skip_scripts=True)
        c2 += c
        t2 += t
        log(f"  -> {c} files, {human(t)}")

    title = args.title or args.slug
    (target / "title.txt").write_text(title + "\n", encoding="utf-8")

    log("")
    log(f"done: {target}")
    log(f"  game/ = {c1 + c2} files, {human(t1 + t2)}")
    log(f"  title.txt = {title!r}")
    log("")
    log("拷到 iPad：把整个文件夹放到 「本应用/Documents/games/」 下，"
        "最终路径 …/Documents/games/%s/game/…" % (args.slug,))

    return 0


if __name__ == "__main__":
    sys.exit(main())