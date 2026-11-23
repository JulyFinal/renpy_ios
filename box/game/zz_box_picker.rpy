# =============================================================================
# zz_box_picker.rpy —— RenPyBox（共用一个 ipa 装多个游戏）的"开局选择器"
#
# 机制（关键，别改坏）：
#   1. base/main.py 被 scripts/box_main_patch.py 改过，启动时会读
#      <Documents>/current_game.txt：
#        * 读到有效 slug -> 把 <Documents>/games/<slug>/game 插进 searchpath，
#          于是本次启动加载的就是那个游戏的脚本（RENPY_SEARCHPATH 机制，
#          renpy/main.py:351 调 renpy.__main__.predefined_searchpath()）；
#        * 读不到 -> 把 <basedir>/picker 插进 searchpath，也就是本脚本，
#          同时设 RENPY_SKIP_MAIN_MENU=1，直接跑 label start。
#   2. 本选择器把游戏列出来；点一下就把 slug 写进 current_game.txt，
#      然后退出 App（renpy.quit()）。用户再点一次图标，就进游戏了。
#      —— 为什么必须重启进程：脚本枚举发生在 init 代码之前，同一个进程里
#      没法把"选择器脚本"换成"游戏脚本"。
#
# 字体：Ren'Py 默认的 DejaVuSans **没有中文字形**（实测"选择"渲染成豆腐），
# 所以 fonts/SourceHanSansLite.ttf（来自 SDK 的 sdk-fonts/，2.9MB，含完整
# 简体中文）由 scripts/box_project.py 复制进来，这里显式指定。
# =============================================================================

init -100 python:
    import os as _box_os

    # 中文字体（box_project.py 保证它存在；可用环境变量覆盖）
    _box_font = _box_os.environ.get("RENPY_BOX_FONT", "fonts/SourceHanSansLite.ttf")

    def _box_docs():
        """App 的 Documents 目录。

        两个环境变量名都认：RENPY_IOS_BOX_DOCS 是 base/main.py 注入块设的，
        RENPY_IOS_DOCS 是早期版本用的名字（保留兼容）。都拿不到时再从
        config.savedir（= <Documents>/saves/<slug>）反推。
        """
        for _k in ("RENPY_IOS_BOX_DOCS", "RENPY_IOS_DOCS"):
            _v = _box_os.environ.get(_k, "")
            if _v:
                return _v
        try:
            return _box_os.path.dirname(_box_os.path.dirname(renpy.config.savedir))
        except Exception:
            return ""

    def _box_games_root():
        d = _box_docs()
        if not d:
            return ""
        return _box_os.path.join(d, "games")

    def _box_human_size(n):
        try:
            n = float(n)
        except Exception:
            return "?"
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024.0 or unit == "GB":
                if unit == "B":
                    return "%d %s" % (n, unit)
                return "%.1f %s" % (n, unit)
            n /= 1024.0
        return "?"

    def _box_scan():
        """扫描 Documents/games/<slug>/game/，返回 [(slug, title, size_text), ...]。"""
        root = _box_games_root()
        rv = []

        if not root:
            return rv

        try:
            names = sorted(_box_os.listdir(root))
        except Exception:
            return rv

        for n in names:
            if n.startswith("."):
                continue

            base = _box_os.path.join(root, n)
            gamedir = _box_os.path.join(base, "game")

            if not _box_os.path.isdir(gamedir):
                continue

            title = n
            try:
                f = open(_box_os.path.join(base, "title.txt"), "rb")
                t = f.read().decode("utf-8", "replace").strip()
                f.close()
                if t:
                    title = t
            except Exception:
                pass

            total = 0
            for dirpath, dirnames, filenames in _box_os.walk(gamedir):
                for fn in filenames:
                    try:
                        total += _box_os.path.getsize(_box_os.path.join(dirpath, fn))
                    except Exception:
                        pass

            rv.append((n, title, _box_human_size(total)))

        return rv

    def _box_choose(slug):
        """写 current_game.txt 然后退出 App，下次启动就进这个游戏。"""
        d = _box_docs()
        if not d:
            return

        fn = _box_os.path.join(d, "current_game.txt")
        try:
            f = open(fn, "wb")
            f.write(slug.encode("utf-8"))
            f.close()
        except Exception:
            renpy.notify("写入失败: %s" % fn)
            return

        renpy.quit()

    def _box_rescan():
        store._box_items = _box_scan()

    # 屏幕尺寸：不依赖 gui.init，直接定成 1920x1080（跟两个游戏一致）。
    config.screen_width = 1920
    config.screen_height = 1080

    # 选择器不需要存档，但 Ren'Py 启动时会建 savedir，给个固定名字。
    config.save_directory = "RenPyOSBox"


default _box_items = [ ]


# 所有文字都走中文字体（DejaVuSans 没有中文字形）
style box_text is default:
    font _box_font
    size 32
    color "#ffffff"

style box_title is box_text:
    size 88

style box_sub is box_text:
    size 28
    color "#8f9bb3"

style box_item is box_text:
    size 52

style box_meta is box_text:
    size 30
    color "#7f8aa3"

style box_enter is box_text:
    size 36
    color "#ffd479"


screen _box_picker():

    # 背景
    add Solid("#0e1016")

    # 标题区
    vbox:
        xpos 0.5
        ypos 90
        xanchor 0.5
        spacing 16

        text "选择游戏" style "box_title" xalign 0.5
        text "游戏放在「文件」App：「本应用/Documents/games/<名字>/game/」" style "box_sub" xalign 0.5

    # 游戏列表
    if _box_items:

        vpgrid:
            cols 1
            ysize 640
            spacing 20
            xpos 0.5
            ypos 270
            xanchor 0.5
            xsize 1500
            mousewheel True
            draggable True

            for _slug, _title, _size in _box_items:

                button:
                    xfill True
                    ysize 132
                    background Solid("#1b2030")
                    hover_background Solid("#2b3550")
                    action Function(_box_choose, _slug)

                    hbox:
                        xpos 40
                        yalign 0.5
                        spacing 30

                        text "[_title!q]" style "box_item"
                        text "[_size!q]" style "box_meta" yalign 0.5 xoffset 20

                    text "进入  >" style "box_enter" xalign 0.97 yalign 0.5

    else:

        vbox:
            xpos 0.5
            ypos 0.55
            xanchor 0.5
            yanchor 0.5
            spacing 24

            text "还没有游戏" style "box_title" color "#ff7b7b" xalign 0.5
            text "把游戏文件夹整个复制到 Documents/games/<名字>/ 下（里面要有 game/ 子目录）" style "box_sub" xalign 0.5
            text "可以用 USB 传，或在「文件」App 里拖进去" style "box_meta" xalign 0.5

            textbutton "重新扫描" action Function(_box_rescan) text_style "box_enter" xalign 0.5

    # 底部说明
    text "注意：点一下游戏会退出 App，再点一次图标就会进入选中的游戏。" style "box_meta" xpos 0.5 xanchor 0.5 ypos 1015


label start:

    $ _box_rescan()

    # 选择器点按钮会直接 renpy.quit()，不会返回到这里。
    call screen _box_picker

    return