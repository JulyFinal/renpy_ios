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

    # ------------------------------------------------------------------
    # 0. 让 SDL 按「横屏」创建窗口（关键，否则画面只显示在左上角）
    # ------------------------------------------------------------------
    # SDL2 的 iOS 后端建窗口时这么定尺寸：
    #   SDL_uikitvideo.m  UIKit_ComputeViewFrame():
    #       frame     = uiwindow.bounds  （= uiscreen.bounds，竖屏时 420x912 点）
    #       landscape = IsLandscape(statusBarOrientation) ||
    #                   !(supported_orientations & (Portrait|PortraitUpsideDown))
    #       fullscreen 且 landscape != (frame 宽 > 高)  ->  交换 w/h
    #   SDL_uikitwindow.m  UIKit_GetSupportedOrientations():
    #       先看 SDL_HINT_ORIENTATIONS（环境变量 SDL_IOS_ORIENTATIONS，空格分隔），
    #       没设才回落到 info.plist 的 UISupportedInterfaceOrientations。
    #
    # 坑：statusBarOrientation 从 iOS 13 起已废弃，iOS 26/27 上恒为 Portrait，
    # 而 LiveContainer 这类宿主又允许竖屏，于是 landscape=False，不交换 ——
    # 窗口被当成竖屏 420x912 点、帧缓冲 1260x2736，在横屏屏幕上只能看到
    # 左上角 1260x1260，其余全黑（真机实测就是这个现象）。
    #
    # 真正的修法（iPhone Air / iOS 27.2 真机实测确认）：
    #   LiveContainer 里把这个 app 的 Orientation Lock 设成 Landscape
    #   （即 LCAppInfo.plist 的 LCOrientationLock = 1）。
    #   LC 的 TweakLoader 会 swizzle UIViewController.__supportedInterfaceOrientations
    #   等三个方法，并强制 scene 的 interfaceOrientation = LandscapeRight，SDL 于是
    #   拿到横屏窗口：
    #       raw.pg_get_size   = (912, 420)      raw.pg_drawable = (2736, 1260)
    #       drawable_viewport = (249, 0, 2238, 1260)  -> 画面正常铺满
    #   用 SideStore / AltStore / Sideloadly 单独安装时不需要这一步，
    #   app 自己的 Info.plist 就声明了横屏。
    #
    # 下面设 SDL_IOS_ORIENTATIONS 是**额外兜底**：在 iOS 27 + LiveContainer 上
    # 实测无效 —— UIKit_GetSupportedOrientations() 里 `(valid & mask) == 0` 会把
    # mask 回退成宿主支持的方向，而 LC 默认是竖屏，所以 hint 被丢弃。留着只是
    # 以防别的宿主 / 老版本行为不同。
    # 想关掉：设 RENPY_IOS_ORIENTATIONS=none。
    if getattr(renpy, "ios", False) or _ios_sys.platform == "ios":
        _renpy_ios_hint = _ios_os.environ.get("RENPY_IOS_ORIENTATIONS", "LandscapeLeft LandscapeRight")
        if _renpy_ios_hint.strip().lower() != "none":
            try:
                _ios_os.environ["SDL_IOS_ORIENTATIONS"] = _renpy_ios_hint
                print("[renpy-ios] SDL_IOS_ORIENTATIONS=%r" % (_renpy_ios_hint,))
            except Exception as _e:
                print("[renpy-ios] cannot set SDL_IOS_ORIENTATIONS: %r" % (_e,))

    # ------------------------------------------------------------------
    # 0.5 构建期容忍缺图（MilfyCity 这类游戏会在 init 里量图片尺寸）
    # ------------------------------------------------------------------
    # 有些游戏在 init python 阶段就调 renpy.image_size()，比如 MilfyCity 的
    # scripts/gui/computer/scenes_gallery/scenes_gallery_setup.rpy:4 里
    # MaxScale2()/MinScale2() 会给画廊里每张图算缩放比例，而它们的调用点在
    # 同一个 init python 块里（scenes_gallery_images.rpy 的 Scenes_GalleryItem(...)）。
    #
    # 我们的素材是**外置**的（iPad 上 Documents/game/），而 ios_create 阶段是
    # 在 Mac 上跑的：项目里没有图片，renpy.image_size() 直接 IOError，
    # 整个 init 失败 → ios_create 拿不到 dump → 构建失败。
    #
    # 以前的做法是 build_ios_ipa.sh --media <PC 上的素材目录>，但那要求 CI 先
    # 下载/解压 1.1 GB 素材。这里改成把 renpy.image_size 包一层：**只在文件
    # 真的不存在时**返回一个占位尺寸（1920x1080），并打一行警告。
    # 游戏跑起来时素材都在，走的是真实尺寸，行为完全不变。
    # 想关掉：设 RENPY_IOS_STRICT_IMAGES=1。

    if not _ios_os.environ.get("RENPY_IOS_STRICT_IMAGES"):
        try:
            _renpy_ios_real_image_size = renpy.image_size

            def _renpy_ios_image_size(im):
                try:
                    return _renpy_ios_real_image_size(im)
                except Exception as e:
                    print("[renpy-ios] image_size fallback (1920x1080) for %r: %r" % (im, e))
                    return (1920, 1080)

            renpy.image_size = _renpy_ios_image_size
        except Exception as _e:
            print("[renpy-ios] cannot wrap renpy.image_size: %r" % (_e,))

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

    # ------------------------------------------------------------------
    # 缓解（不是根治）：当 SDL 仍上报竖屏尺寸时，把宽高交换成横屏再交给 Ren'Py。
    # ------------------------------------------------------------------
    # 注意：这只让 Ren'Py 算出一份「横屏 viewport」，但底层帧缓冲如果真的只有
    # 1260 宽，画面仍然会在 x≈1260 处被切掉（真机上实测从「只露左上角一条」
    # 变成「露出左侧约 45%」）。**根治必须靠 LiveContainer 的朝向锁设成
    # Landscape**（见上面第 0 段）；朝向锁设对之后 raw 值本来就是横屏，
    # 这段是完全空操作。
    # ------------------------------------------------------------------
    # 现象（未修时）：get_size() = (420,912) 点、get_drawable_size() = (1260,2736)
    # 像素，renpy/gl2/gl2draw.pyx:538-543 据此算出
    #   physical_box=(0,338,420,236) -> drawable_viewport=(0,1014,1260,708)
    # 只覆盖屏幕左上角 1260x246 的一条带。
    #
    # 这层包装只在上报尺寸仍是竖屏（w < h）时才交换，正常情况是空操作：
    #   ratio = min(912/1920, 420/1080) = 0.3889 -> view=(746,420)
    #   physical_box=(83,0,746,420) -> viewport=(249,0,2238,1260)
    # gl2draw.pyx 用 `import pygame_sdl2 as pygame` 后按属性查找调用
    # （:538 `renpy.display.core.get_size()`、:543/:669 `pygame.display.get_drawable_size()`），
    # 所以替换模块属性即可生效，且必须在 init 阶段（早于 Interface.set_mode）。
    # 想关掉：设 RENPY_IOS_DISPLAY_MODE=none。

    _renpy_ios_raw_display = { }

    def _renpy_ios_landscape(t):
        try:
            if t and len(t) >= 2 and t[0] < t[1]:
                return (t[1], t[0])
        except Exception:
            pass
        return t

    def _renpy_ios_fix_display_metrics():

        try:
            if _ios_os.environ.get("RENPY_IOS_DISPLAY_MODE", "auto") == "none":
                print("[renpy-ios] display metrics fix disabled")
                return
        except Exception:
            pass

        if not (getattr(renpy, "ios", False) or _ios_sys.platform == "ios"):
            return

        try:
            import pygame_sdl2 as _pg
        except Exception as e:
            print("[renpy-ios] display metrics fix skipped: %r" % (e,))
            return

        disp = getattr(_pg, "display", None)
        if disp is None:
            print("[renpy-ios] display metrics fix skipped: no pygame_sdl2.display")
            return

        def _wrap(orig):
            def wrapper(*args, **kwargs):
                return _renpy_ios_landscape(orig(*args, **kwargs))
            wrapper._renpy_ios_wrapped = True
            return wrapper

        patched = [ ]

        for name in ("get_size", "get_drawable_size"):
            orig = getattr(disp, name, None)
            if orig is None or getattr(orig, "_renpy_ios_wrapped", False):
                continue
            # 保留未包装的原函数，方便诊断（zz_ios_probe.rpy 会读它）。
            _renpy_ios_raw_display[name] = orig
            try:
                setattr(disp, name, _wrap(orig))
                patched.append(name)
            except Exception as e:
                print("[renpy-ios] cannot patch display.%s: %r" % (name, e))

        if patched:
            print("[renpy-ios] display metrics patched (portrait -> landscape): %s" % (", ".join(patched),))

    _renpy_ios_apply()
    _renpy_ios_fix_display_metrics()