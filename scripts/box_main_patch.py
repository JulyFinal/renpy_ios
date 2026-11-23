#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
box_main_patch.py —— 把 ios_create 生成的 Xcode 工程改造成 RenPyBox

做两件事：

1. 往 `<project>/base/main.py` 里注入一段 bootstrap（py2 代码），改写
   `predefined_searchpath()` 与 `path_to_saves()`：

     * 读 `<Documents>/current_game.txt`（一次性，读完即删）
       - 命中且 `<Documents>/games/<slug>/game` 存在 -> 本次启动加载这个游戏，
         searchpath = [<docs>/games/<slug>/game, <basedir>/game, common]
       - 没命中 -> 加载选择器，searchpath = [<basedir>/picker, <basedir>/game, common]，
         并设 RENPY_SKIP_MAIN_MENU=1，让它直接跑 label start
     * path_to_saves() 改成 `<Documents>/saves/<slug>/`，每个游戏互不污染

   为什么改 main.py 就够了：`renpy/main.py:350-351` 与 `:473` 只通过
   `renpy.__main__.path_to_common / predefined_searchpath / path_to_saves`
   这三个函数拿路径，而这个 app 的 `renpy.__main__` 就是 base/main.py。

2. 把 `base/game/` 拆成：
     * `base/picker/`  —— 选择器脚本（zz_box_picker.rpyc）
     * `base/game/`    —— 只留 zz_ios_patch.rpyc / zz_ios_build.rpyc（两个模式下都要加载）

用法：
    python3 scripts/box_main_patch.py /path/to/dist/xcode
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

MARKER = "# ==== renpy_ios box bootstrap"

# ---------------------------------------------------------------------------
# 注入到 base/main.py 的代码。
#
# 注意：base/main.py 由 renios 生成，运行在 Python 2.7 上（Ren'Py 7.7.3）。
# 所以这里**不能**用 f-string / pathlib / type hints，只能 %-格式化和 os 模块。
# ---------------------------------------------------------------------------
OVERRIDE = '''
# ==== renpy_ios box bootstrap (injected by scripts/box_main_patch.py) ====
#
# 这个 app 同时装多个游戏：
#   <Documents>/games/<slug>/game/     -- 每个游戏的脚本+素材
#   <Documents>/saves/<slug>/          -- 每个游戏独立的存档
#   <Documents>/current_game.txt       -- 一次性选择文件（选择器写入，这里读完删掉）
#
# 下面两个函数覆盖了原来的同名实现，Ren'Py 引擎只通过这两个入口拿路径，
# 所以不需要改引擎源码。

_RENPY_IOS_BOX_ORIG_PATH_TO_SAVES = path_to_saves
_RENPY_IOS_BOX_ORIG_PREDEFINED_SEARCHPATH = predefined_searchpath
_RENPY_IOS_BOX_STATE = {}


def _renpy_ios_box_docs(gamedir=None):
    """返回 Documents 目录（games/ 与 saves/ 都在它下面）；拿不到返回 ""。"""

    d = _RENPY_IOS_BOX_STATE.get("docs")
    if d:
        return d

    d = os.environ.get("RENPY_IOS_BOX_DOCS", "")

    if not d:
        # iOS 上原版 path_to_saves 就是 NSDocumentDirectory；桌面调试时让它退化。
        try:
            import renpy
            if renpy.ios:
                d = _RENPY_IOS_BOX_ORIG_PATH_TO_SAVES(gamedir or renpy.config.gamedir)
        except Exception:
            d = ""

    if d:
        d = os.path.abspath(d)
        _RENPY_IOS_BOX_STATE["docs"] = d
        os.environ["RENPY_IOS_BOX_DOCS"] = d
        os.environ["RENPY_IOS_BOX"] = "1"

    return d


def _renpy_ios_box_take_choice(docs):
    """读 Documents/current_game.txt（读完即删），返回合法的 slug 或 ""。"""

    fn = os.path.join(docs, "current_game.txt")

    slug = ""
    try:
        f = open(fn, "rb")
        slug = f.read().decode("utf-8", "replace").strip()
        f.close()
    except Exception:
        slug = ""

    # 一次性：无论是否合法都删掉，这样"退出再打开"一定回到选择器。
    try:
        if os.path.exists(fn):
            os.unlink(fn)
    except Exception:
        pass

    if not slug:
        return ""

    # 只允许简单的 slug，挡住 ".." 之类。
    clean = ""
    for ch in slug:
        if ch.isalnum() or ch in "-_.":
            clean += ch
    slug = clean

    if not slug:
        return ""

    gd = os.path.join(docs, "games", slug, "game")

    if not os.path.isdir(gd):
        print("[renpy-ios-box] choice %r has no game/ dir; going back to picker" % (slug,))
        return ""

    return slug


def predefined_searchpath(commondir):
    """决定本次启动加载哪套脚本。"""

    import renpy

    gamedir = renpy.config.gamedir
    basedir = renpy.config.basedir

    docs = _renpy_ios_box_docs(gamedir)

    if not docs:
        # 不是 iOS 或者拿不到 Documents：退回原版行为。
        return _RENPY_IOS_BOX_ORIG_PREDEFINED_SEARCHPATH(commondir)

    slug = _renpy_ios_box_take_choice(docs)
    _RENPY_IOS_BOX_STATE["slug"] = slug

    sp = []

    if slug:
        sp.append(os.path.join(docs, "games", slug, "game"))
        os.environ["RENPY_IOS_SLUG"] = slug
        os.environ.pop("RENPY_SKIP_MAIN_MENU", None)
        print("[renpy-ios-box] game: %s" % (slug,))
    else:
        os.environ.pop("RENPY_IOS_SLUG", None)
        picker = os.path.join(basedir, "picker")
        if os.path.isdir(picker):
            sp.append(picker)
        os.environ["RENPY_SKIP_MAIN_MENU"] = "1"
        print("[renpy-ios-box] picker")

    # base/game 永远在：里面有 zz_ios_patch.rpyc（显示修正）和 zz_ios_build.rpyc。
    sp.append(gamedir)

    # 保留原版语义：RENPY_SEARCHPATH 用 "::" 分隔，追加在中间。
    if "RENPY_SEARCHPATH" in os.environ:
        for i in os.environ["RENPY_SEARCHPATH"].split("::"):
            if i:
                sp.append(i)

    if commondir and os.path.isdir(commondir):
        sp.append(commondir)

    print("[renpy-ios-box] searchpath:")
    for i in sp:
        print("    %s" % (i,))

    return sp


def path_to_saves(gamedir, save_directory=None):
    """每个游戏一个独立存档目录。"""

    docs = _renpy_ios_box_docs(gamedir)

    if not docs:
        return _RENPY_IOS_BOX_ORIG_PATH_TO_SAVES(gamedir, save_directory)

    slug = _RENPY_IOS_BOX_STATE.get("slug") or "picker"
    d = os.path.join(docs, "saves", slug)

    if save_directory:
        d = os.path.join(d, save_directory)

    try:
        if not os.path.isdir(d):
            os.makedirs(d)
    except Exception:
        pass

    return d

# ==== end renpy_ios box bootstrap ====
'''


def log(msg: str) -> None:
    print(f"[box_main_patch] {msg}")


def ensure_utf8_decl(text: str) -> str:
    """保证 base/main.py 带 UTF-8 编码声明。

    这**不是**可选项。base/main.py 由 Ren'Py 7.7.3 内嵌的 **Python 2.7** 执行，
    而本文件注入的 OVERRIDE 里有中文注释/文档字符串。按 PEP 263，py2 在没有
    coding 声明时遇到非 ASCII 字节会直接::

        SyntaxError: Non-ASCII character '\\xe4' ... but no encoding declared

    结果就是 App 启动瞬间脚本解析失败 —— 表现是**整屏全黑、没有任何日志、没有
    任何 .pyc/缓存生成**（实测踩过一次，排查了很久）。所以这里无条件补上声明，
    声明放在第 1 行即可（PEP 263 允许第 1 或第 2 行）。
    """

    for line in text.split("\n")[:2]:
        if "coding" in line:
            return text
    return "# -*- coding: utf-8 -*-\n" + text


def patch_main_py(main_py: Path) -> bool:
    if not main_py.is_file():
        log(f"ERROR: {main_py} not found")
        return False

    text = main_py.read_text(encoding="utf-8", errors="surrogateescape")

    if MARKER in text:
        log("base/main.py already patched, skipping")
        text = ensure_utf8_decl(text)
        main_py.write_text(text, encoding="utf-8", errors="surrogateescape")
        return True

    idx = text.find("\ndef main(")
    if idx < 0:
        idx = text.find("\nif __name__ == \"__main__\"")
    if idx < 0:
        log("ERROR: can't find insertion point in base/main.py")
        return False

    text = text[: idx + 1] + OVERRIDE + "\n\n" + text[idx + 1 :]
    text = ensure_utf8_decl(text)

    main_py.write_text(text, encoding="utf-8", errors="surrogateescape")

    log(f"patched {main_py} (+{len(OVERRIDE)} bytes, utf-8 decl ensured)")
    return True


KEEP_IN_GAME = (
    "zz_ios_patch.rpyc",
    "zz_ios_build.rpyc",
    "script_version.txt",
)


def relayout_base(basedir: Path) -> bool:
    """base/game -> base/picker，然后在 base/game 里只留公共脚本。"""

    game_dir = basedir / "game"
    picker_dir = basedir / "picker"

    if not game_dir.is_dir():
        log(f"ERROR: {game_dir} not found")
        return False

    if picker_dir.exists():
        log(f"removing old {picker_dir}")
        shutil.rmtree(picker_dir)

    log(f"moving {game_dir} -> {picker_dir}")
    shutil.move(str(game_dir), str(picker_dir))

    game_dir.mkdir()

    for name in KEEP_IN_GAME:
        src = picker_dir / name
        if src.is_file():
            shutil.move(str(src), str(game_dir / name))

    log("base/picker/:")
    for p in sorted(picker_dir.rglob("*")):
        if p.is_file():
            log(f"  {p.relative_to(basedir)}  ({p.stat().st_size} bytes)")

    log("base/game/:")
    for p in sorted(game_dir.rglob("*")):
        if p.is_file():
            log(f"  {p.relative_to(basedir)}  ({p.stat().st_size} bytes)")

    if not (picker_dir / "zz_box_picker.rpyc").is_file():
        log("WARNING: base/picker/zz_box_picker.rpyc missing (picker will not run)")

    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="turn an ios_create project into RenPyBox")
    ap.add_argument("project", help="the xcode project directory produced by ios_create")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    basedir = project / "base"

    if not basedir.is_dir():
        log(f"ERROR: {basedir} not found (is this an ios_create output?)")
        return 1

    if not patch_main_py(basedir / "main.py"):
        return 1

    if not relayout_base(basedir):
        return 1

    (project / "ios-box.json").write_text(
        '{\n  "kind": "renpy-ios-box",\n  "base": "base"\n}\n',
        encoding="utf-8",
    )

    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())