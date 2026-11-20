# =============================================================================
# 临时诊断用：把渲染几何信息画到屏幕四个角。
#
# 只有 patch_game.py 带 --diag 时才会被注入到项目里，正常情况下不在包内。
# 用途：iOS 上画面错位/只显示一角时，直接从手机截图上读出
#       virtual / physical / drawable 三套尺寸，判断是哪一环算错了。
#
# 四个角各放一份文本，哪个角还在屏幕里就能读到；
# 另外四角各有一个色块：红=左上 绿=右上 蓝=左下 黄=右下。
# =============================================================================

init -1900 python:

    _ios_diag_cache = None

    def _ios_diag_text():
        """收集一次几何信息，拼成多行字符串（结果缓存）。"""

        global _ios_diag_cache
        if _ios_diag_cache is not None:
            return _ios_diag_cache

        rows = []

        def add(key, fn):
            try:
                rows.append("%s=%r" % (key, fn()))
            except Exception as e:
                rows.append("%s=<err %s>" % (key, e))

        add("cfg_wh", lambda: (renpy.config.screen_width, renpy.config.screen_height))

        try:
            import pygame_sdl2
            add("pg_win", lambda: pygame_sdl2.display.get_size())
            add("pg_drawable", lambda: pygame_sdl2.display.get_drawable_size())
        except Exception as e:
            rows.append("pygame_sdl2=<err %s>" % (e,))

        try:
            info = renpy.display.get_info()
            add("dispinfo_wh", lambda: (info.current_w, info.current_h))
        except Exception as e:
            rows.append("dispinfo=<err %s>" % (e,))

        draw = renpy.display.draw
        for attr in ("virtual_size", "physical_size", "drawable_size",
                     "physical_box", "drawable_viewport", "dpi_scale",
                     "draw_per_phys", "draw_per_virt"):
            add("d." + attr, (lambda a=attr: getattr(draw, a)))

        try:
            add("iface_dpi", lambda: renpy.display.interface.dpi_scale)
        except Exception as e:
            rows.append("iface_dpi=<err %s>" % (e,))

        add("variants", lambda: ",".join(sorted(renpy.config.variants)))
        add("flags", lambda: "mobile=%r ios=%r touch=%r"
            % (renpy.mobile, renpy.ios, renpy.touch))

        # 每行最多两条，避免一行太长超出 1920 宽度被裁掉
        lines = []
        for i in range(0, len(rows), 2):
            lines.append("   ".join(rows[i:i + 2]))

        _ios_diag_cache = "\n".join(lines)
        return _ios_diag_cache


init 999 python:
    # 浮在所有界面之上；overlay_screens 每帧重画，不会阻断交互
    if "ios_diag" not in renpy.config.overlay_screens:
        renpy.config.overlay_screens.append("ios_diag")


screen ios_diag():

    zorder 250

    $ _dt = _ios_diag_text()

    for _pos in [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]:
        fixed:
            xpos _pos[0]
            ypos _pos[1]
            xanchor _pos[0]
            yanchor _pos[1]
            text _dt size 28 color "#00ff00" outlines [(1, "#000000", 0, 0)]

    add Solid("#ff0000") xysize (140, 140) xpos 0 ypos 0
    add Solid("#00ff00") xysize (140, 140) xalign 1.0 ypos 0
    add Solid("#0000ff") xysize (140, 140) xpos 0 yalign 1.0
    add Solid("#ffff00") xysize (140, 140) xalign 1.0 yalign 1.0