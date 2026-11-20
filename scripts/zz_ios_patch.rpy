# -*- coding: utf-8 -*-
# Ren'Py iOS 运行期补丁 —— 由 scripts/patch_game.py 注入，请勿手改仓库里的副本。
#
# 作用：让 iOS 上「文件」App 能看到的 Documents/game/ 变成一个额外的素材根目录。
#
# 原理（renpy/main.py + renpy/loader.py 的真实行为）：
#   * trasfn() 对 config.searchpath 里的每一项做 os.path.join(config.basedir, d, name)，
#     d 为绝对路径时 os.path.join 会丢弃 basedir，因此绝对路径可以直接生效；
#   * load_from_archive() 里 afn = transfn(prefix)，所以 config.archives 里只能放
#     **相对 basename**（如 "archive"），不能塞绝对路径；
#   * main.py 在 init 代码执行完之后（约 :604）会再调一次 index_archives()，
#     注释写明 "because the list of known archives may have changed"，
#     因此我们在 init python 里改 config.archives 是官方支持的时机。
#
# 目录布局（iPad 上「文件」App → 我的 iPad → <游戏名>）：
#   Documents/game/archive.rpa
#   Documents/game/audio/...
#   Documents/game/images/...
#
# 素材分卷时（tools/make_payload.py 产出的多个 zip）解压出来是：
#   Documents/game/...          <- part1
#   Documents/game_part2/...    <- part2
# 下面会把 Documents 下所有以 game 开头的目录都收进 searchpath，
# 所以不需要在 iPad 上把两个目录合并（iOS 的「文件」App 很难合并同名目录）。

init -2000 python:

    import os as _ios_os
    import sys as _ios_sys

    def _renpy_ios_candidate_dirs():
        """
        返回按优先级排列的外部素材目录候选列表（绝对路径）。
        """

        rv = [ ]

        # 调试 / 自救 / 构建期用：环境变量里给了就最优先。
        # 支持用 os.pathsep（macOS/Linux 是 ":"，Windows 是 ";"）分隔多个目录，
        # 因为 make_payload.py 分卷时素材会散在 game/、game_part2/ 里。
        # build_ios_ipa.sh --media 就是靠这个变量，让 ios_create 阶段能读到图片
        # （有些游戏在 init 里就调 renpy.image_size()，没有图会直接启动失败）。
        env = _ios_os.environ.get("RENPY_IOS_GAME_DIR")
        if env:
            for _p in env.split(_ios_os.pathsep):
                _p = _p.strip()
                if _p:
                    rv.append(_p)

        try:
            savedir = renpy.config.savedir
        except Exception:
            savedir = None

        if savedir:
            savedir = _ios_os.path.abspath(savedir)

            # iOS: config.savedir 就是 NSDocumentDirectory，
            # 也就是 <App 容器>/Documents，正是「文件」App 能看到的那一层。
            #
            # 素材可能被切成好几卷（GitHub Release 单附件上限 2 GiB），
            # 解压出来是 game/、game_part2/、game_part3/……，这里全都收。
            try:
                _names = sorted(_ios_os.listdir(savedir))
            except Exception:
                _names = [ "game" ]

            for _n in _names:
                if not _n.startswith("game"):
                    continue
                _p = _ios_os.path.join(savedir, _n)
                if _ios_os.path.isdir(_p):
                    rv.append(_p)

            # 兜底：<App 容器>/game（模拟器里手放文件时用得上）
            rv.append(_ios_os.path.join(_ios_os.path.dirname(savedir), "game"))

        return rv

    def _renpy_ios_apply():

        added = [ ]
        found = [ ]

        for d in _renpy_ios_candidate_dirs():
            d = _ios_os.path.normpath(d)

            if not _ios_os.path.isdir(d):
                continue

            found.append(d)

            # 插到最前面：外部素材优先于内置素材。
            if d not in renpy.config.searchpath:
                renpy.config.searchpath.insert(0, d)

            # 注册该目录下的 .rpa（引擎也会自己扫 searchpath，这里显式兜底）。
            try:
                names = sorted(_ios_os.listdir(d))
            except Exception:
                names = [ ]

            for fn in names:
                base, ext = _ios_os.path.splitext(fn)
                if ext.lower() != ".rpa":
                    continue
                if not _ios_os.path.isfile(_ios_os.path.join(d, fn)):
                    continue
                if base not in renpy.config.archives:
                    renpy.config.archives.insert(0, base)
                added.append(fn)

        if found:
            try:
                renpy.loader.index_archives()
            except Exception as e:
                print("[renpy-ios] index_archives failed: %r" % (e,))

        if found:
            print("[renpy-ios] external game dir: %s" % (", ".join(found),))
            print("[renpy-ios] external archives: %s" % (", ".join(added) or "(none)",))
        else:
            print("[renpy-ios] no external game dir found; tried: %s" % (", ".join(_renpy_ios_candidate_dirs()),))

        # 手机端不要暴露控制台 / 开发者功能。
        try:
            renpy.config.developer = False
        except Exception:
            pass

    _renpy_ios_apply()