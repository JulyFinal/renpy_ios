#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_payload.py —— 把 ipa 里被剔除的素材打成「外置素材包」，供 iPad 用「文件」App 解压。

为什么要有这个东西：
  自签安装（SideStore / AltStore / LiveContainer）对单个 app 的体积很不友好，而这类
  游戏 90% 的体积是图片和音频。所以 ipa 里只留脚本 + 字体 + 翻译（几十 MB），
  大块的图片/音频/.rpa 作为外置素材放进 app 的 Documents/game/，
  由 scripts/zz_ios_patch.rpy 在启动时插进 renpy.config.searchpath。

为什么是 .zip 而且还要分卷：
  * iPad 的「文件」App 能原生解压 .zip，但**不认** .tar.zst / .7z。
  * GitHub Release 单个附件上限 2 GiB，而这些游戏的素材往往 2~4 GB。
    所以按 --part-mb 切成多个 zip，每个 zip 里放一个**不同顶层目录**：
        part1 -> game/
        part2 -> game_part2/
        part3 -> game_part3/ ...
    这样在「文件」App 里逐个解压、再一起拖进 app 的 Documents 即可，不需要合并目录
    （iOS 上合并同名目录非常难操作）。zz_ios_patch.rpy 会把 Documents 下所有
    game / game_partN 目录都加进 searchpath。

哪些文件算「素材」：
  与 scripts/patch_game.py 的 split 规则完全互补 —— 那边留在 ipa 里的
  （game/gui/**、字体、files/**、tl/**）这里就不收，反之亦然。两边都改的话要同步改。

用法：
  python tools/make_payload.py --game "D:/Game/game" --out dist/payload --part-mb 1900
  python tools/make_payload.py --game "..." --out ... --list-only     # 只统计不打包
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile

# 与 patch_game.py 的 split 排除列表保持一致
MEDIA_EXT = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif", ".tga",
    ".ogg", ".opus", ".mp3", ".wav", ".flac", ".m4a", ".oga", ".aac", ".wma",
    ".webm", ".mp4", ".m4v", ".mov", ".ogv", ".avi", ".mkv", ".mpg", ".mpeg",
    ".rpa",
}

SKIP_DIRS = {"saves", "cache", "__pycache__", ".git", ".svn"}
SKIP_FILES = {"thumbs.db", "desktop.ini", ".ds_store", "traceback.txt", "errors.txt", "log.txt"}

MB = 1024 * 1024


def log(msg: str) -> None:
    print("[make_payload] " + msg, flush=True)


def collect(game_dir: str):
    """返回 [(relpath, size), ...]，relpath 用 / 分隔。"""
    out = []
    for root, dirs, files in os.walk(game_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        rel_root = os.path.relpath(root, game_dir)

        for fn in sorted(files):
            low = fn.lower()
            if low in SKIP_FILES or fn.endswith(("~", ".bak", ".orig")):
                continue
            ext = os.path.splitext(low)[1]
            if ext not in MEDIA_EXT:
                continue
            path = os.path.join(root, fn)
            if not os.path.isfile(path):
                continue
            rel = fn if rel_root == "." else os.path.join(rel_root, fn)
            out.append((rel.replace(os.sep, "/"), os.path.getsize(path)))
    return out


def plan_parts(files, part_bytes):
    """贪心分卷：大的先放，每次塞进当前最小的那卷。"""
    if not files:
        return []

    total = sum(s for _, s in files)
    n = max(1, (total + part_bytes - 1) // part_bytes)
    n = min(n, len(files))

    buckets = [[] for _ in range(n)]
    sizes = [0] * n
    for rel, size in sorted(files, key=lambda x: -x[1]):
        i = sizes.index(min(sizes))
        buckets[i].append((rel, size))
        sizes[i] += size

    parts = [(b, s) for b, s in zip(buckets, sizes) if b]
    # 顶层目录名：第一个叫 game，其余 game_partN
    named = []
    for i, (b, s) in enumerate(parts):
        top = "game" if i == 0 else "game_part%d" % (i + 1)
        named.append((top, b, s))
    return named


def write_zip(zip_path, top, entries, game_dir, compress):
    mode = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    with zipfile.ZipFile(zip_path, "w", allowZip64=True) as zf:
        for i, (rel, _size) in enumerate(entries, 1):
            src = os.path.join(game_dir, rel.replace("/", os.sep))
            zf.write(src, arcname=top + "/" + rel, compress_type=mode)
            if i % 200 == 0:
                log("  %s: %d/%d" % (os.path.basename(zip_path), i, len(entries)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build external asset payload zips")
    ap.add_argument("--game", required=True, help="source game/ directory (the PC one)")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--part-mb", type=int, default=1900,
                    help="max uncompressed size per zip part (GiB Release limit is 2048)")
    ap.add_argument("--compress", action="store_true",
                    help="deflate instead of store (slower, rarely worth it for media)")
    ap.add_argument("--list-only", action="store_true")
    args = ap.parse_args(argv)

    game_dir = os.path.abspath(args.game)
    if not os.path.isdir(game_dir):
        log("ERROR: %s not found" % game_dir)
        return 2

    files = collect(game_dir)
    if not files:
        log("ERROR: no payload files found under %s" % game_dir)
        return 3

    total = sum(s for _, s in files)
    log("%d files, %.1f MB total" % (len(files), total / MB))

    parts = plan_parts(files, args.part_mb * MB)
    for top, entries, size in parts:
        log("  %-12s %4d files  %8.1f MB" % (top, len(entries), size / MB))

    if args.list_only:
        return 0

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    manifest = {"parts": [], "total_files": len(files), "total_bytes": total}
    for i, (top, entries, size) in enumerate(parts, 1):
        zip_path = os.path.join(out, "assets.part%d.zip" % i)
        log("writing %s ..." % zip_path)
        write_zip(zip_path, top, entries, game_dir, args.compress)
        manifest["parts"].append(dict(
            file=os.path.basename(zip_path),
            top_dir=top,
            files=len(entries),
            bytes=size,
            zip_bytes=os.path.getsize(zip_path),
        ))
        log("  -> %.1f MB" % (os.path.getsize(zip_path) / MB))

    with open(os.path.join(out, "assets-manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)

    log("done: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())