#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_game_source.py —— 把 PC 版游戏目录里「该进 git 的那部分」同步到 games/<Game>/game/。

仓库只放**体积小、必须跟代码一起版本化**的那部分：
    *.rpy / *.rpymc / *.rpyc（脚本）
    game/tl/**（翻译）
    game/gui/**（UI 素材 + 字体，通常几十 MB 以内）
    game/files/**（MilkyTouch 这类把 .rpyc 藏在 files/ 的游戏）
    game/presplash.*、game/icon.*（启动图 / 图标）

不放进仓库的：图片、音频、视频、*.rpa —— 这些由 tools/make_payload.py 打成
「外置素材包」，走 GitHub Release，玩家在 iPad 上解压进 App 的 Documents/game/。

另一条规则：**同名 .rpyc 存在时，丢弃那个 .rpy**（只留 .rpyc）。
  理由（实测）：
    1. .rpyc 才是玩家实际运行的字节码。很多压缩版/汉化版把 .rpy 用 unrpyc
       反编译回来当"源码"塞进去，里面是有语法错误的残次品 —— MilfyCity 的
       game/scripts/rps.rpy:347 就是 `show paper_selection:` 后面跟空块，
       用 .rpy 编译直接报 "show statement expects a non-empty block"。
    2. 原版目录里 .rpyc 的 mtime 永远比 .rpy 新，所以游戏一直用的是 .rpyc。
       但 git checkout 出来的 mtime 不可靠，两个都留着会随机选中坏源码。
    3. 7.4.11 编的 .rpyc 在 7.7.3 SDK 下能正常加载（已实测：MilfyCity 的
       1396 个 .rpyc 全部载入成功）。
  MilkyTouch 更极端：只有 1 个 .rpy、121 个 .rpyc，且 .rpyc 魔数被改成
  RENPY RPC3（patch_game.py 会改回 RPC2）。

用法：
  python tools/sync_game_source.py --game "D:/MilfyCity/game" --out games/MilfyCity/game
  python tools/sync_game_source.py --game "..." --out ... --dry-run
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

MEDIA_EXT = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif", ".tga",
    ".ogg", ".opus", ".mp3", ".wav", ".flac", ".m4a", ".oga", ".aac", ".wma",
    ".webm", ".mp4", ".m4v", ".mov", ".ogv", ".avi", ".mkv", ".mpg", ".mpeg",
    ".rpa",
}

SKIP_DIRS = {"saves", "cache", "__pycache__", ".git", ".svn"}
SKIP_FILES = {"thumbs.db", "desktop.ini", ".ds_store", "traceback.txt", "errors.txt", "log.txt"}

# 这些顶层目录里的图片/音频**照样收**（它们是 UI，不是大素材）
ALWAYS_DIRS = ("gui", "tl", "files")

# 不管放在哪都要收的根文件
ALWAYS_ROOT = ("presplash", "icon", "splashscreen")

MB = 1024 * 1024


def log(msg: str) -> None:
    print("[sync_source] " + msg, flush=True)


def keep_dir(rel_dir: str) -> bool:
    top = rel_dir.split("/")[0].lower()
    return top in ALWAYS_DIRS


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sync small game sources into the repo")
    ap.add_argument("--game", required=True, help="source game/ directory")
    ap.add_argument("--out", required=True, help="destination, e.g. games/MilfyCity/game")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--clean", action="store_true", help="wipe --out first")
    args = ap.parse_args(argv)

    src = os.path.abspath(args.game)
    dst = os.path.abspath(args.out)
    if not os.path.isdir(src):
        log("ERROR: %s not found" % src)
        return 2

    # 第一遍：哪些 .rpy 旁边已经有 .rpyc（那就不要这个 .rpy）
    compiled = set()
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith((".rpyc", ".rpymc")):
                rel = os.path.relpath(os.path.join(root, fn), src).replace(os.sep, "/")
                compiled.add(rel.rsplit(".", 1)[0])

    if args.clean and os.path.isdir(dst) and not args.dry_run:
        log("cleaning %s" % dst)
        shutil.rmtree(dst)

    picked = []
    total = 0

    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        rel_root = os.path.relpath(root, src).replace(os.sep, "/")
        rel_root = "" if rel_root == "." else rel_root
        in_always = keep_dir(rel_root) if rel_root else False

        for fn in sorted(files):
            low = fn.lower()
            if low in SKIP_FILES or fn.endswith(("~", ".bak", ".orig")):
                continue

            rel = (rel_root + "/" + fn) if rel_root else fn
            ext = os.path.splitext(low)[1]
            stem = rel[: -len(ext)] if ext else rel

            # 已有 .rpyc 就不要那个（可能是反编译残次的）.rpy
            if ext == ".rpy" and stem in compiled:
                continue

            if ext in MEDIA_EXT and not in_always:
                # 根目录的 presplash/icon 之类的图片例外
                if not (rel_root == "" and stem.lower().split("/")[-1] in ALWAYS_ROOT):
                    continue

            if ext in (".rpyb",):
                continue

            picked.append(rel)
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass

    picked.sort()
    log("%d files, %.1f MB" % (len(picked), total / MB))

    by_top = {}
    for rel in picked:
        by_top.setdefault(rel.split("/")[0], 0)
        by_top[rel.split("/")[0]] += 1
    for k in sorted(by_top):
        log("  %-16s %5d files" % (k, by_top[k]))

    if args.dry_run:
        return 0

    for rel in picked:
        s = os.path.join(src, rel.replace("/", os.sep))
        d = os.path.join(dst, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)

    log("done: %s" % dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())