#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_game.py —— 把一个 PC 版 Ren'Py 游戏组装成可被 `ios_create` 打包的项目目录。

做的事：
  1. 把游戏 game/ 复制到 <out>/game（跳过 saves/、cache/、系统垃圾文件）
  2. 注入 scripts/zz_ios_patch.rpy（运行期把 Documents/game 加进 searchpath）
     和 scripts/zz_ios_cheat.rpy（左上角 GM 悬浮按钮 / 改数值的面板，--no-cheat 可关）
  3. 生成 <out>/game/zz_ios_build.rpy（构建期规则：改 config.name / 排除源码 /
     可选地把图片音视频剔出 ipa，让它们走外置素材）
  4. 校验 SDK 版本与游戏 script_version.txt 是否兼容

用法：
  python3 patch_game.py --sdk /path/renpy-7.7.3-sdk \
      --game /path/to/Game/game --out /path/to/work/MyGame \
      --name MyGame --display-name "My Game" --version 1.0.0 [--no-split]

设计说明（重要，别随手改）：
  * renpy/common/00build.rpy L92 的 ("**.rpa", None) 属于 **renpy_patterns**，只作用于
    SDK 自己的 renpy/ 目录，**不作用于游戏 game/ 里的 .rpa**（实测：MilkyTouch 的
    archive.rpa 1.32GB 原样进了 base/）。而 ios_populate 又是用 noarchive=True 调
    Distributor，即不会生成新的 .rpa。所以 split 模式下必须自己
    `build.classify("**.rpa", None)` 把游戏自带的 .rpa 剔出去，作为「外置素材」交给
    玩家放进 Documents/game/，由 zz_ios_patch.rpy 注册进 config.archives。
  * build.classify() 追加到 base_patterns，dump 出来的匹配顺序是
    early + base + late，且**第一条命中的规则生效**。所以「保留 game/gui」这条必须写在
    「排除 **.png」之前。
  * 匹配到 None 的**目录**会直接剪枝（distribute.rpy:790 `if file_list is None: return`），
    不会继续往下走，所以按后缀排除比按目录排除更稳（游戏里的素材目录名五花八门）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

# ---------------------------------------------------------------------------
# 构建期注入的 .rpy（用 %(...)s 模板，避免与 Ren'Py 的 [ ] 插值冲突）
# ---------------------------------------------------------------------------

BUILD_RPY = '''\
# -*- coding: utf-8 -*-
# 由 scripts/patch_game.py 生成，请勿手改。
# 只影响构建（build.*），不影响游戏逻辑。

init -1600 python:
    # iOS 上 config.save_directory 不参与路径计算（见 renpy.py path_to_saves），
    # 这里只是让桌面端调试时不要把存档写进仓库。
    config.save_directory = "RenPyIOS"

init -1400 python:

    # ---- 源码 / 缓存一律不进包 -------------------------------------------
    # 注意：renpy/common/00build.rpy 在 init -1500 才建立 build store，
    # 所以这里不能用更早的优先级，否则 NameError。
    # 又因为 build.classify() 是「先追加先命中」，用 -1400 可以让这些规则
    # 排在游戏自己的 options.rpy（init 0）之前，从而覆盖它的分类。
    build.name = %(name)r
    build.directory_name = %(name)r + "-" + %(version)r

    build.classify("**.rpy", None)
    build.classify("**.rpym", None)
    build.classify("**.py", None)
    build.classify("**.sh", None)
    build.classify("**.psd", None)
    build.classify("game/cache/**", None)
    build.classify("game/saves/**", None)
    build.classify("**~", None)
    build.classify("**.bak", None)
    build.classify("**.orig", None)
    build.classify("**.DS_Store", None)
    build.classify("**Thumbs.db", None)
    build.classify("**desktop.ini", None)

    if %(split)r:
        # ---- 保留项必须写在排除项前面（首条命中生效）--------------------
        # gui 是运行时 UI 素材，必须留在 app 里。
        build.classify("game/gui/**", "all")
        # 字体、脚本、翻译也留下。
        build.classify("game/**.ttf", "all")
        build.classify("game/**.otf", "all")
        build.classify("game/**.ttc", "all")
        build.classify("game/files/**", "all")
        build.classify("game/tl/**", "all")

        # 启动图 / 图标这类根目录小图也必须留在包里，
        # 否则会被下面的 "**.jpg" / "**.png" 一起踢出去，启动画面变白屏。
        build.classify("game/presplash.*", "all")
        build.classify("game/splashscreen.*", "all")
        build.classify("game/icon.*", "all")
        build.classify("game/android-icon-*", "all")

        # ---- 大块素材剔出 ipa，改走外置素材 ------------------------------
        for _pat in [
            "**.png", "**.jpg", "**.jpeg", "**.webp", "**.gif", "**.bmp",
            "**.avif", "**.tga",
            "**.ogg", "**.opus", "**.mp3", "**.wav", "**.flac", "**.m4a",
            "**.oga", "**.aac", "**.wma",
            "**.webm", "**.mp4", "**.m4v", "**.mov", "**.ogv", "**.avi",
            "**.mkv", "**.mpg", "**.mpeg",
        ]:
            build.classify(_pat, None)

        # 游戏自带的 .rpa 也走外置素材（默认并不会被排除，见文件头说明）。
        build.classify("**.rpa", None)
        # 附带的一键通关存档包，装到 app 里没用。
        build.classify("game/*-saves.zip", None)

init 999 python:
    # 最后再抢一次名字：不少游戏自己在 options.rpy 里写了 config.name /
    # config.version（MilkyTouch 就是 config.name = "Milky Touch"），会把
    # init -1600 里的值覆盖掉。而 launcher 是在 main.py:584 调
    # renpy.dump.dump() 之后才读 dump 的，所以 init 999 改的值仍然生效。
    #
    # 这一点很重要：dump 里的 name 会被 create_project() 写进 Xcode 的
    # target 名和 PRODUCT_NAME，带空格或中文会让 xcodebuild -target 很难写。
    config.name = %(name)r
    config.version = %(version)r
'''

PATCH_RPY = "zz_ios_patch.rpy"
CHEAT_RPY = "zz_ios_cheat.rpy"
DIAG_RPY = "zz_ios_diag.rpy"

SKIP_DIRS = {"saves", "cache", "__pycache__", ".git", ".svn"}
SKIP_FILES = {
    "thumbs.db",
    "desktop.ini",
    ".ds_store",
    "traceback.txt",
    "errors.txt",
    "log.txt",
}


def log(msg: str) -> None:
    print("[patch_game] " + msg, flush=True)


def read_script_version(game_dir: str):
    fn = os.path.join(game_dir, "script_version.txt")
    if not os.path.isfile(fn):
        return None
    try:
        with open(fn, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read().strip()
    except OSError:
        return None
    nums = re.findall(r"\d+", txt)
    if not nums:
        return None
    return tuple(int(i) for i in nums[:3])


def read_sdk_version(sdk: str):
    fn = os.path.join(sdk, "renpy", "vc_version.py")
    if os.path.isfile(fn):
        try:
            with open(fn, "r", encoding="utf-8", errors="replace") as f:
                txt = f.read()
            # vc_version.py 里是  version = u'7.7.3.24061702'
            m = re.search(r"^version\s*=\s*u?[\"']([0-9]+(?:\.[0-9]+)*)", txt, re.M)
            if m:
                return tuple(int(i) for i in m.group(1).split(".")[:3])
        except OSError:
            pass

    fn = os.path.join(sdk, "renpy", "versions.py")
    if os.path.isfile(fn):
        try:
            with open(fn, "r", encoding="utf-8", errors="replace") as f:
                txt = f.read()
            m = re.search(r"version_tuple\s*=\s*\(([^)]*)\)", txt)
            if m:
                return tuple(int(i) for i in re.findall(r"\d+", m.group(1))[:3])
        except OSError:
            pass

    return None


def copytree_game(src: str, dst: str) -> None:
    os.makedirs(dst, exist_ok=True)
    n = 0
    total = 0

    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)

        rel = os.path.relpath(root, src)
        target_root = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target_root, exist_ok=True)

        for fn in sorted(files):
            if fn.lower() in SKIP_FILES:
                continue
            if fn.endswith(("~", ".bak", ".orig")):
                continue
            s = os.path.join(root, fn)
            if not os.path.isfile(s):
                continue
            shutil.copy2(s, os.path.join(target_root, fn))
            n += 1
            try:
                total += os.path.getsize(s)
            except OSError:
                pass

    log("copied %d files (%.1f MB)" % (n, total / (1024.0 * 1024.0)))


# ---------------------------------------------------------------------------
# .rpyc 头规范化
# ---------------------------------------------------------------------------
#
# 有些「整合版 / 反破解版」游戏把 renpy/script.py 里的
#     RPYC2_HEADER = b"RENPY RPC2"
# 改成了
#     RPYC2_HEADER = b"RENPY RPC3"
# （常量名不变，只改字面量，目的是让 unrpyc 之类工具解析失败）。
# 官方 SDK 只认 RPC2，于是 load_appropriate_file() 会报
#     Exception: Could not load file .../game/files/XXX.rpyc
#
# 因为字节码载荷本身没变（两边 script.py 逐字节只差这一行），
# 只需把每个 .rpyc/.rpymc 的前 10 个字节 RENPY RPC3 改回 RENPY RPC2。

RPC3 = b"RENPY RPC3"
RPC2 = b"RENPY RPC2"


def normalize_rpyc_headers(game_dir: str) -> int:
    fixed = 0

    for root, dirs, files in os.walk(game_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for fn in files:
            if not fn.lower().endswith((".rpyc", ".rpymc")):
                continue

            path = os.path.join(root, fn)
            try:
                with open(path, "rb") as f:
                    head = f.read(10)
            except OSError:
                continue

            if head != RPC3:
                continue

            try:
                with open(path, "r+b") as f:
                    f.write(RPC2)
            except OSError as e:
                log("WARNING: could not patch header of %s: %s" % (path, e))
                continue

            fixed += 1

    if fixed:
        log("normalized RENPY RPC3 -> RPC2 in %d .rpyc file(s)" % fixed)
    return fixed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Assemble a Ren'Py project for ios_create")
    ap.add_argument("--sdk", required=True, help="Ren'Py SDK root (contains renpy/, renios/)")
    ap.add_argument("--game", required=True, help="source game/ directory")
    ap.add_argument("--out", required=True, help="output project directory (will hold game/)")
    ap.add_argument("--name", required=True, help="ASCII project name, becomes the Xcode target")
    ap.add_argument("--display-name", default=None, help="CFBundleDisplayName")
    ap.add_argument("--version", default="1.0.0", help="CFBundleShortVersionString")
    ap.add_argument("--split", dest="split", action="store_true", default=True,
                    help="keep images/audio out of the ipa (default)")
    ap.add_argument("--no-split", dest="split", action="store_false",
                    help="bundle everything into the ipa")
    ap.add_argument("--no-cheat", dest="cheat", action="store_false", default=True,
                    help="don't inject zz_ios_cheat.rpy (the GM / cheat panel)")
    ap.add_argument("--diag", action="store_true",
                    help="inject zz_ios_diag.rpy: draws render geometry on screen")
    args = ap.parse_args(argv)

    sdk = os.path.abspath(args.sdk)
    src_game = os.path.abspath(args.game)
    out = os.path.abspath(args.out)

    if not os.path.isdir(os.path.join(sdk, "renpy")):
        log("ERROR: %s does not look like a Ren'Py SDK (no renpy/)" % sdk)
        return 2
    if not os.path.isdir(src_game):
        log("ERROR: game dir not found: %s" % src_game)
        return 2

    if not os.path.isdir(os.path.join(sdk, "renios")):
        log("NOTICE: %s/renios is missing; ios_create will refuse to run." % sdk)
        log("NOTICE: download renpy-<ver>-renios.zip and unpack it into the SDK root.")

    name = re.sub(r"[^-_A-Za-z0-9]", "", args.name) or "project"
    display_name = args.display_name or args.name
    version = args.version

    sdk_ver = read_sdk_version(sdk)
    game_ver = read_script_version(src_game)
    log("sdk version   : %s" % (".".join(map(str, sdk_ver)) if sdk_ver else "unknown"))
    log("game version  : %s" % (".".join(map(str, game_ver)) if game_ver else "unknown"))
    if sdk_ver and game_ver and sdk_ver[:2] != game_ver[:2]:
        log("WARNING: SDK %s and game %s differ in major.minor; .rpyc bytecode may not load."
            % (".".join(map(str, sdk_ver)), ".".join(map(str, game_ver))))

    dst_game = os.path.join(out, "game")
    if os.path.isdir(dst_game):
        log("clearing %s" % dst_game)
        shutil.rmtree(dst_game)
    os.makedirs(out, exist_ok=True)

    log("copying game assets ...")
    copytree_game(src_game, dst_game)

    normalize_rpyc_headers(dst_game)

    patch_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), PATCH_RPY)
    if not os.path.isfile(patch_src):
        log("ERROR: %s is missing" % patch_src)
        return 3
    shutil.copy2(patch_src, os.path.join(dst_game, PATCH_RPY))
    log("injected %s" % PATCH_RPY)

    if args.cheat:
        cheat_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), CHEAT_RPY)
        if not os.path.isfile(cheat_src):
            log("ERROR: %s is missing" % cheat_src)
            return 3
        shutil.copy2(cheat_src, os.path.join(dst_game, CHEAT_RPY))
        log("injected %s (GM button / cheat panel)" % CHEAT_RPY)
    else:
        log("skipped %s (--no-cheat)" % CHEAT_RPY)

    if args.diag:
        diag_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), DIAG_RPY)
        if os.path.isfile(diag_src):
            shutil.copy2(diag_src, os.path.join(dst_game, DIAG_RPY))
            log("injected %s (diagnostic overlay; remove before release)" % DIAG_RPY)
        else:
            log("WARNING: --diag given but %s is missing" % diag_src)

    build_rpy = BUILD_RPY % dict(
        name=name,
        version=version,
        split=bool(args.split),
    )
    with open(os.path.join(dst_game, "zz_ios_build.rpy"), "w", encoding="utf-8", newline="\n") as f:
        f.write(build_rpy)
    log("generated zz_ios_build.rpy (split=%s, name=%s, version=%s)"
        % (args.split, name, version))

    meta = dict(
        name=name,
        display_name=display_name,
        bundle_version=version,
        bundle_id="com.domain." + name,
        split=bool(args.split),
        sdk_version=".".join(map(str, sdk_ver)) if sdk_ver else None,
        game_version=".".join(map(str, game_ver)) if game_ver else None,
    )
    with open(os.path.join(out, "renpy_ios_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)

    log("done: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())