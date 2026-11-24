#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 PC 版 game/saves 里的存档，整理成 RenPyBox 能直接看见的样子。

为什么需要这个工具
------------------
Ren'Py 的存档槽名规则是 ``page + "-" + slot``（见
``renpy/common/00action_file.rpy`` 的 ``__slotname()``）。磁盘上就是
``<page>-<slot>-LT1.save``，auto / quick 那两类特殊页的前缀是
``auto-`` / ``quick-``。

PC 版玩家留下的存档，绝大多数是 ``auto-1`` … ``auto-N``（自动存档轮转）。
这些文件只在加载界面的 **A（自动存档）页** 才有对应格子，普通页 1、2、3…
里永远看不到它们 —— 所以把 PC 存档原样搬进盒子，打开「加载」会觉得
「存档没了」。

这个工具做的事：把 ``auto-*`` / ``quick-*`` / ``_reload-*`` 这些特殊槽，
按时间从新到旧重新编号成普通页槽（``1-1``、``1-2``、……、``2-1``…），
这样它们会像普通存档一样出现在「加载」的第 1 页、第 2 页……

顺带还做两件防御：
* 跳过引擎大版本比盒子（7.x）新的存档 —— 8.x 的存档在 7.x 上读不了，
  摆出来只会让玩家点了报错。
* 默认不动 ``persistent``（画廊/音乐解锁）。想连它一起换，加
  ``--persistent``。

用法
----
    python tools/import_saves.py \
        --saves "C:/path/to/Game/game/saves" \
        --out   "_stage/saves/milfyCity" \
        --per-page 4

``--per-page`` 要和目标游戏的 ``gui.file_slot_cols * gui.file_slot_rows``
一致（MilkyTouch 是 3x2=6，MilfyCity 是 2x2=4），否则会算出界外的槽名。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import zipfile

SAVE_RE = re.compile(r"^(?P<page>[A-Za-z_]+|\d+)-(?P<slot>[A-Za-z0-9_]+)\.save$")
SPECIAL_PREFIXES = ("auto-", "quick-", "_reload-")


def read_save_meta(path: str) -> dict:
    """读 .save（其实是个 zip）里的引擎版本和 json 信息。"""
    meta: dict = {"version": None, "json": None}
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "renpy_version" in names:
                raw = z.read("renpy_version").decode("utf-8", "replace")
                meta["version"] = raw.strip()
            if "json" in names:
                try:
                    meta["json"] = json.loads(z.read("json").decode("utf-8", "replace"))
                except Exception:
                    pass
            meta["has_screenshot"] = "screenshot.png" in names
    except Exception as exc:  # 坏档不该让整个流程停下
        meta["error"] = str(exc)
    return meta


def engine_major(version) -> int | None:
    if not version:
        return None
    m = re.search(r"(\d+)\.(\d+)", version)
    if not m:
        return None
    return int(m.group(1))


def plan(saves_dir: str, per_page: int, max_major: int) -> tuple[list, list]:
    """返回 (要搬的存档, 跳过的存档)。要搬的按时间从新到旧排好序。"""
    files = []
    for name in sorted(os.listdir(saves_dir)):
        if not name.endswith(".save"):
            continue
        path = os.path.join(saves_dir, name)
        if not os.path.isfile(path):
            continue
        meta = read_save_meta(path)
        major = engine_major(meta.get("version"))
        is_special = name.startswith(SPECIAL_PREFIXES)
        files.append(
            {
                "name": name,
                "path": path,
                "mtime": os.path.getmtime(path),
                "meta": meta,
                "major": major,
                "special": is_special,
            }
        )

    keep, skip = [], []
    for item in files:
        if item["major"] is not None and item["major"] > max_major:
            skip.append((item, "引擎 %s 比盒子新" % item["meta"]["version"]))
            continue
        keep.append(item)

    # 时间新的排前面：玩家最想接着玩的是最近那次。
    keep.sort(key=lambda i: -i["mtime"])

    out = []
    for idx, item in enumerate(keep):
        page = idx // per_page + 1
        slot = idx % per_page + 1
        target = "%d-%d-LT1.save" % (page, slot)
        out.append(dict(item, target=target, page=page, slot=slot))
    return out, skip


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把 PC 存档整理成盒子可见的普通存档槽")
    ap.add_argument("--saves", required=True, help="PC 版 game/saves 目录")
    ap.add_argument("--out", required=True, help="整理结果的输出目录")
    ap.add_argument("--per-page", type=int, default=6,
                    help="每页槽数 = gui.file_slot_cols * gui.file_slot_rows（默认 6）")
    ap.add_argument("--max-major", type=int, default=7, help="允许的最高引擎大版本（默认 7）")
    ap.add_argument("--persistent", action="store_true", help="连 persistent 一起复制")
    ap.add_argument("--copy", action="store_true", help="复制而不是改名（默认复制，源目录不动）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.saves):
        print("找不到存档目录：%s" % args.saves)
        return 2
    if args.per_page <= 0:
        print("--per-page 必须是正整数")
        return 2

    keep, skip = plan(args.saves, args.per_page, args.max_major)

    print("源目录 : %s" % args.saves)
    print("每页槽数: %d" % args.per_page)
    print("要搬   : %d 个" % len(keep))
    for item in keep:
        print("  %-22s -> %-16s  %s" % (item["name"], item["target"], item["meta"].get("version")))
    if skip:
        print("跳过   : %d 个" % len(skip))
        for item, why in skip:
            print("  %-22s  %s" % (item["name"], why))

    if args.dry_run:
        return 0

    os.makedirs(args.out, exist_ok=True)
    for item in keep:
        dst = os.path.join(args.out, item["target"])
        if args.copy:
            shutil.copy2(item["path"], dst)
        else:
            shutil.move(item["path"], dst)
        print("写入 %s" % dst)

    if args.persistent:
        src = os.path.join(args.saves, "persistent")
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(args.out, "persistent"))
            print("写入 persistent")
    other = os.path.join(args.saves, "navigation.json")
    if os.path.isfile(other):
        shutil.copy2(other, os.path.join(args.out, "navigation.json"))
        print("写入 navigation.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())