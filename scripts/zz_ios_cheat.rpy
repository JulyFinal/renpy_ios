# -*- coding: utf-8 -*-
# =============================================================================
# zz_ios_cheat.rpy —— iOS 触屏「金手指」/ 简易控制台
# -----------------------------------------------------------------------------
# 游戏里常驻一个左上角 GM 悬浮按钮，点开是全屏面板：
#   数值 —— store 里所有 int/float（money、day、好感度……），-/+ 按步长加减，「改」精确输入；
#   对象 —— store 里的自定义对象（例如 MilfyCity 的 inventory），进去改它的数字字段；
#   持久 —— persistent 里的数字和开关；
#   命令 —— 直接执行 Python 表达式/语句，等价于控制台。
#
# 为什么不用引擎自带控制台（00console.rpy）：它靠 Esc / 右键退出，触屏上出不来；
# 而且 zz_ios_patch.rpy 为了保证手机端干净，把 config.developer 关掉了。
#
# 开关：环境变量 RENPY_IOS_CHEAT=0 整体关掉。
# 字体：box 模式默认 fonts/SourceHanSansLite.ttf，可用 RENPY_IOS_CHEAT_FONT 覆盖；
#       独立模式继承游戏自己的字体（汉化游戏都自带中文字体）。
# =============================================================================


# 面板 UI 状态。用 default 而不是普通赋值：default 会在读旧档时补上默认值，
# 并且不会被 init 期的快照当成常量。
default _cheat_tab = u"store"
default _cheat_obj = u""
default _cheat_q = u""
default _cheat_step = 1
default _cheat_edit_ref = None
default _cheat_edit_text = u""
default _cheat_cmd = u""
default _cheat_result = u""


init -100 python:

    import os as _cheat_os
    import sys as _cheat_sys
    import time as _cheat_timem

    # py2 里大整数是 long，要一起算进来。
    try:
        _CHEAT_NUMT = (int, long, float)
    except NameError:
        _CHEAT_NUMT = (int, float)

    # 注意：store 命名空间里的 str 被 Ren'Py 重绑成了 unicode！
    # 所以不能用 isinstance(k, _CHEAT_STRS) —— persistent 字段和对象属性都是字节串键，
    # 只有 default 语句建的变量是 unicode 键。用 basestring 两种都覆盖。
    try:
        _CHEAT_STRS = (basestring,)
    except NameError:
        _CHEAT_STRS = (str,)

    # 不参与扫描的名字（不是数值，列出来只会碍事）。
    _CHEAT_SKIP = set([
        "renpy", "config", "gui", "persistent", "store", "build",
        "preferences", "style", "updater", "im", "mm", "fn",
        "renpy_version_tuple",
        # 下面是 common 脚本里直接赋值（不是 default/define）的引擎变量，
        # renpy.dump.definitions 里查不到，只能点名排除。
        "main_menu", "mouse_visible", "suppress_overlay", "PY2", "PY3",
        "quick_menu", "game_menu_screen", "save_name", "nvl", "nvl_narrator",
    ])

    # 常见「钱 / 点数」关键字，命中的排最前。
    _CHEAT_HOT = ("money", "cash", "gold", "coin", "dollar", "score", "points", "fund")

    # 名字本身就是「钱」的字段：数值页顶部固定铺一行。
    # MilfyCity 的钱是 inventory.money（对象属性），不是 store 变量，
    # 不铺这一行的话用户在数值页里根本翻不到（2026-11-25 用户原话：
    # 「我怀疑这个金币的数值不是直接的而是实时计算的？」）。
    _CHEAT_MONEY_NAMES = set([
        "money", "cash", "gold", "coins", "coin", "dollars", "dollar", "balance", "wallet",
    ])

    _CHEAT_PLAIN_TYPES = set([
        "str", "unicode", "bytes", "int", "long", "float", "bool",
        "list", "tuple", "dict", "set", "frozenset", "NoneType",
        "function", "builtin_function_or_method", "module", "type",
        "method", "instancemethod", "classobj", "generator", "property",
        "NoneType",
    ])

    def _cheat_stamp():
        try:
            return _cheat_timem.strftime("%H:%M:%S", _cheat_timem.localtime())
        except Exception:
            return u"?"

    def _cheat_logfile():
        return _cheat_os.path.join(renpy.config.gamedir, "_cheat_log.txt")

    def _cheat_log(msg):
        # 用 stdout 而不是 print()：minstore 的 print 会强插 checkpoint，init 期不一定安全。
        try:
            _cheat_sys.stdout.write("[cheat] %s\n" % (msg,))
            _cheat_sys.stdout.flush()
        except Exception:
            pass
        # 再往 gamedir 落一份文件：iOS 上 stdout 全靠 zz_ios_patch.rpy 的 tee，
        # tee 没装上的时候日志里一行都看不到（2026-11-24 夜间那几次就是），
        # 这份文件是唯一靠得住的证据。只在少数几个事件里写，不会拖慢。
        try:
            try:
                line = (u"[cheat %s] %s\n" % (_cheat_stamp(), msg)).encode("utf-8")
            except Exception:
                line = "[cheat] log-encode-failed\n"
            f = open(_cheat_logfile(), "ab")
            try:
                f.write(line)
            finally:
                f.close()
        except Exception:
            pass

    def _cheat_enabled():
        try:
            if _cheat_os.environ.get("RENPY_IOS_CHEAT", "") in ("0", "off", "no", "false"):
                return False
            # 只在「选游戏」那个界面里不挂金手指（它的 gamedir 是 base/picker）。
            #
            # 之前是按 RENPY_IOS_SLUG 判断的，但那个环境变量在真机上并不总是传进来：
            # 一旦为空，游戏里也会判成「选择器」→ 直接 return False，GM 按钮根本没装。
            # 2026-11-25 已经踩过一次（用户报「找了半天控制台没出来」）。
            try:
                if _cheat_os.path.basename(str(renpy.config.gamedir).rstrip("/\\")) == "picker":
                    return False
            except Exception:
                pass
            return True
        except Exception:
            return False

    # ---------------------------------------------------------------- 底层读写

    def _cheat_store_mod():
        return _cheat_sys.modules["store"]

    def _cheat_sd():
        try:
            return _cheat_store_mod().__dict__
        except Exception:
            return {}

    def _cheat_pd():
        try:
            return persistent.__dict__
        except Exception:
            return {}

    # ---------------------------------------------------------------- 名字表
    # renpy.dump.definitions 记录了每个 define/default 的 (名字, 文件, 行号)。
    # 用它把「引擎内置变量」和「游戏自己的变量」分开，不然数值页会混进
    # main_menu / mouse_visible 这类 common 脚本里的东西。
    _CHEAT_NAMES = {}

    def _cheat_names():
        if _CHEAT_NAMES.get("ok"):
            return _CHEAT_NAMES
        game = set()
        eng = set()
        try:
            defs = list(renpy.dump.definitions or [])
        except Exception:
            defs = []
        for item in defs:
            try:
                name, fn, ln = item
            except Exception:
                continue
            if not name or not isinstance(name, _CHEAT_STRS):
                continue
            f = (u"%s" % (fn or u"")).replace(u"\\", u"/").lower()
            if u"/common/" in f or f.startswith(u"common/"):
                eng.add(name)
            else:
                game.add(name)
        _CHEAT_NAMES["game"] = game
        _CHEAT_NAMES["eng"] = eng
        _CHEAT_NAMES["ok"] = True
        _cheat_log("names game=%d eng=%d" % (len(game), len(eng)))
        return _CHEAT_NAMES

    def _cheat_hidden_name(k):
        # 引擎定义的、游戏自己没定义的：不展示。
        try:
            n = _cheat_names()
        except Exception:
            return False
        if k in n["game"]:
            return False
        return k in n["eng"]

    def _cheat_ui(name, default=None):
        try:
            v = _cheat_sd().get(name, default)
        except Exception:
            return default
        if v is None:
            return default
        return v

    def _cheat_state(name, value):
        try:
            _cheat_sd()[name] = value
        except Exception:
            pass
        renpy.restart_interaction()

    def _cheat_tab_now():
        return u"%s" % (_cheat_ui("_cheat_tab", u"store"),)

    def _cheat_obj_now():
        return u"%s" % (_cheat_ui("_cheat_obj", u""),)

    def _cheat_q_now():
        return (u"%s" % (_cheat_ui("_cheat_q", u""),)).strip().lower()

    def _cheat_step_now():
        try:
            return int(_cheat_ui("_cheat_step", 1) or 1)
        except Exception:
            return 1

    def _cheat_isnum(v):
        return (not isinstance(v, bool)) and isinstance(v, _CHEAT_NUMT)

    def _cheat_fmt(v):
        try:
            if isinstance(v, bool):
                return u"开" if v else u"关"
            if isinstance(v, float):
                if v == int(v) and abs(v) < 1e15:
                    return u"%d" % int(v)
                return u"%.4f" % v
            return u"%d" % v
        except Exception:
            try:
                return u"%r" % (v,)
            except Exception:
                return u"?"

    def _cheat_cut(s, n=30):
        s = u"%s" % (s,)
        if len(s) > n:
            return s[:n - 1] + u"…"
        return s

    def _cheat_esc(s):
        # Ren'Py 的 text 会把 [ 当插值、{ 当文本标签，动态内容必须转义。
        s = u"%s" % (s,)
        return s.replace(u"[", u"[[").replace(u"{", u"{{")

    def _cheat_parse(txt, old):
        t = (u"%s" % (txt,)).strip()
        if not t:
            return None
        try:
            if isinstance(old, float):
                return float(t)
            return int(t)
        except Exception:
            pass
        try:
            return float(t)
        except Exception:
            return None

    # ref := ("s", 名字)               store 变量
    #        ("p", 名字)               persistent 字段
    #        ("o", 对象名, 字段名)      对象字段

    def _cheat_obj_get(name):
        try:
            return getattr(_cheat_store_mod(), name, None)
        except Exception:
            return None

    def _cheat_rget(ref):
        try:
            k = ref[0]
            if k == "s":
                return getattr(_cheat_store_mod(), ref[1])
            if k == "p":
                return getattr(persistent, ref[1])
            if k == "o":
                obj = _cheat_obj_get(ref[1])
                if obj is None:
                    return None
                return getattr(obj, ref[2])
        except Exception:
            return None
        return None

    def _cheat_rput(ref, value):
        try:
            k = ref[0]
            if k == "s":
                setattr(_cheat_store_mod(), ref[1], value)
            elif k == "p":
                setattr(persistent, ref[1], value)
            elif k == "o":
                obj = _cheat_obj_get(ref[1])
                if obj is None:
                    renpy.notify(u"对象已经不在了")
                    return False
                setattr(obj, ref[2], value)
            else:
                return False
        except Exception as e:
            renpy.notify(u"写入失败：%s" % (e,))
            return False
        renpy.restart_interaction()
        return True

    def _cheat_nudge(ref, sign):
        v = _cheat_rget(ref)
        if not _cheat_isnum(v):
            return
        _cheat_rput(ref, v + sign * _cheat_step_now())

    def _cheat_toggle(ref):
        _cheat_rput(ref, not bool(_cheat_rget(ref)))

    def _cheat_enter(ref):
        _cheat_state("_cheat_obj", ref[1])

    def _cheat_back():
        _cheat_state("_cheat_obj", u"")

    # ---------------------------------------------------------------- 枚举

    def _cheat_obj_fields(obj):
        rv = []
        try:
            d = obj.__dict__
        except Exception:
            return rv
        for k, v in list(d.items()):
            if not isinstance(k, _CHEAT_STRS):
                continue
            if k.startswith("_"):
                continue
            if isinstance(v, bool) or _cheat_isnum(v):
                rv.append(k)
        rv.sort()
        return rv

    def _cheat_obj_candidates():
        rv = []
        for k, v in list(_cheat_sd().items()):
            if not isinstance(k, _CHEAT_STRS):
                continue
            if not k or k.startswith("_") or k in _CHEAT_SKIP:
                continue
            if _cheat_hidden_name(k):
                continue
            if v is None:
                continue
            cls = v.__class__
            if cls.__name__ in _CHEAT_PLAIN_TYPES or cls.__name__ == "_Feature":
                continue
            # 引擎的 Displayable / Character（nvl 之类）不算游戏对象。
            try:
                if isinstance(v, renpy.display.core.Displayable):
                    continue
            except Exception:
                pass
            try:
                if isinstance(v, renpy.character.Character):
                    continue
            except Exception:
                pass
            try:
                mod = getattr(cls, "__module__", "") or ""
            except Exception:
                mod = ""
            # 引擎内部对象（Character、Displayable、Preferences…）一律不列。
            if mod.startswith("renpy") or mod.startswith("_renpy"):
                continue
            if mod in ("sys", "os", "posixpath", "collections", "types"):
                continue
            if not hasattr(v, "__dict__"):
                continue
            if len(_cheat_obj_fields(v)) == 0:
                continue
            rv.append(k)
        rv.sort()
        return rv

    def _cheat_money_refs():
        # [(标签, ref)]：store 里直接叫 money/cash 的变量 + 对象身上的这些字段。
        rv = []
        try:
            sd = _cheat_sd()
        except Exception:
            return rv
        for k in list(sd.keys()):
            if not isinstance(k, _CHEAT_STRS) or not k or k.startswith("_"):
                continue
            if (u"%s" % (k,)).lower() not in _CHEAT_MONEY_NAMES:
                continue
            v = sd.get(k)
            if isinstance(v, bool) or not _cheat_isnum(v):
                continue
            rv.append((u"%s" % (k,), ("s", k)))
        for oname in _cheat_obj_candidates():
            obj = _cheat_obj_get(oname)
            if obj is None:
                continue
            for f in _cheat_obj_fields(obj):
                if (u"%s" % (f,)).lower() not in _CHEAT_MONEY_NAMES:
                    continue
                try:
                    v = getattr(obj, f)
                except Exception:
                    continue
                if isinstance(v, bool) or not _cheat_isnum(v):
                    continue
                rv.append((u"%s.%s" % (oname, f), ("o", oname, f)))
        return rv

    def _cheat_hot(name):
        low = name.lower()
        for h in _CHEAT_HOT:
            if h in low:
                return 0
        return 1

    def _cheat_filter(rv, q):
        if not q:
            return rv
        out = []
        for row in rv:
            try:
                if q in (u"%s" % (row[0],)).lower():
                    out.append(row)
            except Exception:
                pass
        return out

    def _cheat_rows():
        # 返回 [(名字, 值文字, "num"|"bool"|"obj", ref)]
        tab = _cheat_tab_now()
        q = _cheat_q_now()
        rv = []

        if tab == u"obj":
            cur = _cheat_obj_now()
            if cur:
                obj = _cheat_obj_get(cur)
                if obj is None:
                    return []
                for f in _cheat_obj_fields(obj):
                    try:
                        v = getattr(obj, f)
                    except Exception:
                        continue
                    kind = "bool" if isinstance(v, bool) else "num"
                    rv.append((f, _cheat_fmt(v), kind, ("o", cur, f)))
                return _cheat_filter(rv, q)
            for name in _cheat_obj_candidates():
                obj = _cheat_obj_get(name)
                if obj is None:
                    continue
                n = len(_cheat_obj_fields(obj))
                rv.append((name, u"%s · %d" % (obj.__class__.__name__, n), "obj", ("obj", name)))
            return _cheat_filter(rv, q)

        if tab == u"persist":
            d = _cheat_pd()
            for k, v in list(d.items()):
                if not isinstance(k, _CHEAT_STRS) or not k or k.startswith("_"):
                    continue
                if isinstance(v, bool):
                    rv.append((k, _cheat_fmt(v), "bool", ("p", k)))
                elif _cheat_isnum(v):
                    rv.append((k, _cheat_fmt(v), "num", ("p", k)))
            rv.sort(key=lambda r: (_cheat_hot(r[0]), r[0].lower()))
            return _cheat_filter(rv, q)

        d = _cheat_sd()
        pins = _cheat_money_refs()
        pinrefs = set([repr(p[1]) for p in pins])
        for k, v in list(d.items()):
            if not isinstance(k, _CHEAT_STRS) or not k or k.startswith("_") or k in _CHEAT_SKIP:
                continue
            if _cheat_hidden_name(k):
                continue
            if repr(("s", k)) in pinrefs:
                continue
            if isinstance(v, bool):
                rv.append((u"%s" % (k,), _cheat_fmt(v), "bool", ("s", k)))
            elif _cheat_isnum(v):
                rv.append((u"%s" % (k,), _cheat_fmt(v), "num", ("s", k)))
        rv.sort(key=lambda r: (_cheat_hot(r[0]), r[0].lower()))
        pr = []
        for lab, ref in pins:
            pr.append((u"¥ " + lab, _cheat_fmt(_cheat_rget(ref)), "num", ref))
        return _cheat_filter(pr + rv, q)

    # ---------------------------------------------------------------- 精确输入

    def _cheat_edit_open(ref):
        _cheat_state("_cheat_edit_ref", ref)
        _cheat_state("_cheat_edit_text", _cheat_fmt(_cheat_rget(ref)))
        renpy.show_screen("cheat_keypad", target="_cheat_edit_text", mode="num")

    def _cheat_edit_commit():
        ref = _cheat_ui("_cheat_edit_ref", None)
        if not ref:
            return
        val = _cheat_parse(_cheat_ui("_cheat_edit_text", u""), _cheat_rget(ref))
        if val is None:
            renpy.notify(u"这个数字看不懂")
            return
        _cheat_rput(ref, val)

    def _cheat_pad_keys(mode):
        if mode == "num":
            return ["1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0", "-"]
        # 10 列 x 6 行：数字、字母、常用符号（改数值/写表达式够用）。
        rows = [
            "1234567890",
            "qwertyuiop",
            "asdfghjkl_",
            "zxcvbnm.-+",
            ["=", "*", "/", "(", ")", "[", "]", "{", "}", "SP"],
            ["\"", "'", ":", ",", "%", "#", "$", "@", "!", "~"],
        ]
        keys = []
        for row in rows:
            if not isinstance(row, (list, tuple)):
                for c in row:
                    keys.append(c)
            else:
                keys.extend(row)
        return keys

    def _cheat_pad_push(target, ch):
        if ch == "SP":
            ch = " "
        cur = u"%s" % (_cheat_ui(target, u""),)
        cur += ch
        if len(cur) > 80:
            cur = cur[-80:]
        _cheat_state(target, cur)

    def _cheat_pad_back(target):
        cur = u"%s" % (_cheat_ui(target, u""),)
        _cheat_state(target, cur[:-1])

    def _cheat_pad_clear(target):
        _cheat_state(target, u"")

    def _cheat_pad_open(target, mode="num"):
        renpy.show_screen("cheat_keypad", target=target, mode=mode)

    def _cheat_pad_ok(target):
        renpy.hide_screen("cheat_keypad")
        if target == "_cheat_edit_text":
            _cheat_edit_commit()

    # ---------------------------------------------------------------- 命令

    def _cheat_run_cmd():
        from renpy.python import py_compile, py_eval, py_exec
        code = (u"%s" % (_cheat_ui("_cheat_cmd", u""),)).strip()
        if not code:
            return
        isexpr = True
        try:
            py_compile(code, "eval")
        except Exception:
            isexpr = False
        try:
            if isexpr:
                out = u"%r" % (py_eval(code),)
            else:
                py_exec(code)
                out = u"OK"
        except Exception as e:
            out = u"%s: %s" % (e.__class__.__name__, e)
        _cheat_state("_cheat_result", out)
        _cheat_log("cmd: %s -> %s" % (code, out))

    # ---------------------------------------------------------------- 尺寸

    def _cheat_sw():
        try:
            return int(config.screen_width)
        except Exception:
            return 1920

    def _cheat_sh():
        try:
            return int(config.screen_height)
        except Exception:
            return 1080

    def _cheat_pw():
        return int(_cheat_sw() * 0.94)

    def _cheat_ph():
        return int(_cheat_sh() * 0.90)

    def _cheat_lw():
        return _cheat_pw() - 44

    def _cheat_lh():
        return max(120, _cheat_ph() - 176)

    def _cheat_cols():
        return 2 if _cheat_sw() >= 1500 else 1

    def _cheat_rw():
        return (_cheat_lw() - 20) // _cheat_cols() - 6

    def _cheat_nw():
        return int(_cheat_rw() * 0.46)

    def _cheat_vw():
        return int(_cheat_rw() * 0.24)

    # ---------------------------------------------------------------- 安装

    def _cheat_install():
        try:
            open(_cheat_logfile(), "wb").close()
        except Exception:
            pass
        if not _cheat_enabled():
            _cheat_log("disabled gamedir=%s" % (renpy.config.gamedir,))
            return
        try:
            if "cheat_bubble" not in config.overlay_screens:
                config.overlay_screens.append("cheat_bubble")
            # always_shown_screens 在 suppress_overlay 的时候也照样显示：
            # 片头（config.splashscreen_suppress_overlay=True）、主菜单、
            # 以及游戏里 hide_interface 看 CG 的那次 ui.interact(suppress_overlay=True)，
            # overlay_screens 都会被藏起来 —— 两处都挂，GM 才「一定看得见」。
            try:
                if "cheat_bubble" not in config.always_shown_screens:
                    config.always_shown_screens.append("cheat_bubble")
            except Exception:
                pass
            _cheat_log("installed gamedir=%s overlay=%d always=%d" % (
                renpy.config.gamedir,
                len(config.overlay_screens),
                len(getattr(config, "always_shown_screens", []) or [])))
        except Exception as e:
            _cheat_log("install failed: %r" % (e,))


init 0 python:

    # 字体：box 模式必须显式指定中文字体，否则标题全是豆腐块。
    # 必须在 style 语句（同优先级、本文件靠后的 style 块）之前算好。
    #
    # 这里**绝不能留 None**：lint 会拿 style 的 font 去 renpy.loader.loadable()，
    # None 会让它 AttributeError 崩掉（renpy/lint.py:353 `name.lstrip('/')`）。
    # 也要放到 init 0 而不是 -20：游戏 gui.rpy 是 `init offset = -2` 定义的，
    # -20 时 gui.text_font 还没赋值，读不到就只能用 DejaVuSans（中文变豆腐）。
    # 候选必须真的能被 loader 找到，否则 Ren'Py 会报 font not found（box 模式下
    # fonts/SourceHanSansLite.ttf 只在 picker 目录里，游戏模式看不到）。
    def _cheat_use_font(cand):
        if not cand:
            return u""
        try:
            if renpy.loader.loadable(cand):
                return u"%s" % (cand,)
        except Exception:
            pass
        return u""

    _cheat_font = "DejaVuSans.ttf"
    try:
        _cheat_cands = []
        _env_font = _cheat_os.environ.get("RENPY_IOS_CHEAT_FONT", "") or u""
        if _env_font:
            _cheat_cands.append(_env_font)
        if _cheat_os.environ.get("RENPY_IOS_BOX", "") == "1":
            _box_font = _cheat_os.environ.get("RENPY_BOX_FONT", "") or u""
            if _box_font:
                _cheat_cands.append(_box_font)
            _cheat_cands.append(u"fonts/SourceHanSansLite.ttf")
        # 单独打一个游戏时跟着它自己的正文字体走（汉化游戏都自带中文字体）。
        try:
            _gui_font = gui.text_font or u""
        except Exception:
            _gui_font = u""
        if _gui_font:
            _cheat_cands.append(_gui_font)
        for _cand in _cheat_cands:
            _picked = _cheat_use_font(_cand)
            if _picked:
                _cheat_font = _picked
                break
    except Exception:
        _cheat_font = "DejaVuSans.ttf"


style cheat_panel_frame is default:
    background Solid("#0d1117f2")

style cheat_text is default:
    size 26
    color "#dde5ef"
    font _cheat_font

style cheat_title is default:
    size 40
    color "#ffffff"
    font _cheat_font

style cheat_dim is default:
    size 22
    color "#8b9bad"
    font _cheat_font

style cheat_value is default:
    size 26
    color "#9ae6a0"
    font _cheat_font

style cheat_btn is default:
    background Solid("#ffffff1e")
    hover_background Solid("#4a9eff55")
    selected_background Solid("#ffd47944")

style cheat_input is input:
    size 26
    color "#dde5ef"
    font _cheat_font


init 996 python:

    _cheat_install()


init 997 python:

    # 一次性自检：第一次 interact 完把「GM 到底挂上没有」写进 _cheat_log.txt。
    # 真机上没法看屏幕时，这就是唯一能确定原因的线索。
    _cheat_diag_done = [False]

    def _cheat_diag_interact():
        if _cheat_diag_done[0]:
            return
        _cheat_diag_done[0] = True
        try:
            _cheat_log("interact#1 bubble=%r overlay=%r always=%r gdir=%s" % (
                renpy.get_screen("cheat_bubble") is not None,
                "cheat_bubble" in config.overlay_screens,
                "cheat_bubble" in config.always_shown_screens,
                renpy.config.gamedir))
        except Exception as e:
            _cheat_log("diag failed: %r" % (e,))

    config.interact_callbacks.append(_cheat_diag_interact)


screen _cheat_key(lab, act, w=64, h=52, sel=False):

    button:
        style "cheat_btn"
        xsize w
        ysize h
        action act

        text _cheat_esc(lab):
            style "cheat_text"
            xalign 0.5
            yalign 0.5
            color ("#ffd479" if sel else "#dbe4ee")


screen cheat_bubble():

    zorder 1680

    # 做得又大又亮：以前是 96x54 的 60% 黑 + 白字，压在花哨的 CG 上根本看不清，
    # 用户「找了半天」也找不到。现在是黄框 + 深底 + 42 号带描边的 GM。
    button:
        xpos 12
        ypos 10
        xsize 152
        ysize 80
        background Solid("#ffd23fee")
        hover_background Solid("#8fd0ffee")
        padding (5, 5)
        action Show("cheat_panel")

        frame:
            background Solid("#0b0f14f2")
            xysize (142, 70)
            padding (0, 0)

            text "GM":
                style "cheat_text"
                xalign 0.5
                yalign 0.5
                size 42
                bold True
                color "#ffd23f"
                outlines [ (3, "#000000cc", 0, 0) ]

    # 桌面 / 模拟器上按 F9 也能开，方便调试（iOS 不会发这个键）。
    key "K_F9" action Show("cheat_panel")


screen cheat_panel():

    modal True
    zorder 1700

    add Solid("#000000cc")

    $ _ct_tab = _cheat_tab_now()
    $ _ct_step = _cheat_step_now()
    $ _ct_obj = _cheat_obj_now()

    frame:
        style "cheat_panel_frame"
        xalign 0.5
        yalign 0.5
        xsize _cheat_pw()
        ysize _cheat_ph()
        padding (22, 14)

        fixed:
            xysize (_cheat_pw() - 44, _cheat_ph() - 28)

            # ------------------------------------------------ 标题 + 页签 + 步长
            hbox:
                xpos 0
                ypos 0
                spacing 12

                text "金手指" style "cheat_title" yalign 0.5

                null width 8

                use _cheat_key("数值", SetVariable("_cheat_tab", u"store"), 92, 48, _ct_tab == u"store")
                use _cheat_key("对象", SetVariable("_cheat_tab", u"obj"), 92, 48, _ct_tab == u"obj")
                use _cheat_key("持久", SetVariable("_cheat_tab", u"persist"), 92, 48, _ct_tab == u"persist")
                use _cheat_key("命令", SetVariable("_cheat_tab", u"cmd"), 92, 48, _ct_tab == u"cmd")

                if _ct_tab != u"cmd":
                    null width 14

                    text "步长" style "cheat_dim" yalign 0.5
                    use _cheat_key("1", SetVariable("_cheat_step", 1), 54, 48, _ct_step == 1)
                    use _cheat_key("10", SetVariable("_cheat_step", 10), 60, 48, _ct_step == 10)
                    use _cheat_key("100", SetVariable("_cheat_step", 100), 70, 48, _ct_step == 100)
                    use _cheat_key("1k", SetVariable("_cheat_step", 1000), 64, 48, _ct_step == 1000)
                    use _cheat_key("10k", SetVariable("_cheat_step", 10000), 70, 48, _ct_step == 10000)
                    use _cheat_key("100k", SetVariable("_cheat_step", 100000), 80, 48, _ct_step == 100000)

            # ------------------------------------------------ 关闭
            button:
                style "cheat_btn"
                xalign 1.0
                ypos 0
                xsize 84
                ysize 48
                action Hide("cheat_panel")

                text "关闭":
                    style "cheat_text"
                    xalign 0.5
                    yalign 0.5

            # ------------------------------------------------ 筛选 / 返回
            if _ct_tab != u"cmd":
                hbox:
                    xpos 0
                    ypos 66
                    spacing 10

                    if _ct_tab == u"obj" and _ct_obj:
                        use _cheat_key("← 返回", Function(_cheat_back), 108, 44)

                    text "筛选" style "cheat_dim" yalign 0.5

                    frame:
                        background Solid("#ffffff18")
                        padding (10, 4)
                        xsize 420
                        ysize 44

                        input:
                            value VariableInputValue("_cheat_q")
                            length 24
                            pixel_width 396
                            style "cheat_input"

                    use _cheat_key("小键盘", Function(_cheat_pad_open, "_cheat_q", "text"), 108, 44)
                    use _cheat_key("清空", SetVariable("_cheat_q", u""), 76, 44)

            # ------------------------------------------------ 列表 / 命令
            if _ct_tab == u"cmd":

                vbox:
                    xpos 0
                    ypos 76
                    spacing 12
                    xsize _cheat_lw()

                    text "输入 Python 表达式或语句，直接作用于 store。例如 money = 99999 或 inventory.money = 5000" style "cheat_dim"

                    frame:
                        background Solid("#ffffff18")
                        padding (12, 6)
                        xsize _cheat_lw()
                        ysize 56

                        input:
                            value VariableInputValue("_cheat_cmd")
                            length 200
                            pixel_width (_cheat_lw() - 40)
                            style "cheat_input"

                    hbox:
                        spacing 12
                        use _cheat_key("执行", Function(_cheat_run_cmd), 100, 48)
                        use _cheat_key("小键盘", Function(_cheat_pad_open, "_cheat_cmd", "text"), 108, 48)
                        use _cheat_key("清空", SetVariable("_cheat_cmd", u""), 82, 48)

                    text "结果" style "cheat_dim"

                    frame:
                        background Solid("#00000055")
                        padding (12, 8)
                        xsize _cheat_lw()
                        ysize 150

                        text _cheat_esc(u"%s" % (_cheat_ui("_cheat_result", u""),)) style "cheat_value"

            else:

                vpgrid:
                    xpos 0
                    ypos 124
                    xsize _cheat_lw()
                    ysize _cheat_lh()
                    cols _cheat_cols()
                    spacing 8
                    mousewheel True
                    draggable True

                    for _lab, _val, _kind, _ref in _cheat_rows():

                        hbox:
                            xsize _cheat_rw()
                            ysize 54
                            spacing 8
                            yalign 0.5

                            text _cheat_esc(_cheat_cut(_lab)):
                                style "cheat_text"
                                xsize _cheat_nw()
                                yalign 0.5

                            fixed:
                                xsize _cheat_vw()
                                ysize 54

                                text _cheat_esc(_val):
                                    style "cheat_value"
                                    xalign 1.0
                                    yalign 0.5

                            fixed:
                                xsize 176
                                ysize 54

                                hbox:
                                    xalign 1.0
                                    yalign 0.5
                                    spacing 8

                                    if _kind == "num":
                                        use _cheat_key("-", Function(_cheat_nudge, _ref, -1), 52, 46)
                                        use _cheat_key("+", Function(_cheat_nudge, _ref, 1), 52, 46)
                                        use _cheat_key("改", Function(_cheat_edit_open, _ref), 52, 46)
                                    elif _kind == "bool":
                                        use _cheat_key("切换", Function(_cheat_toggle, _ref), 92, 46)
                                    else:
                                        use _cheat_key("进入", Function(_cheat_enter, _ref), 92, 46)

            # ------------------------------------------------ 底部提示
            text "数值立刻生效；改坏了大不了读档，改完最好存一次档。" style "cheat_dim" xpos 0 yalign 1.0

    key "K_ESCAPE" action Hide("cheat_panel")


screen cheat_keypad(target, mode="num"):

    modal True
    zorder 1800

    $ _ct_val = u"%s" % (_cheat_ui(target, u""),)

    add Solid("#000000aa")

    frame:
        style "cheat_panel_frame"
        xalign 0.5
        yalign 0.5
        padding (20, 16)

        vbox:
            spacing 10

            text "输入" style "cheat_dim"

            frame:
                background Solid("#ffffff14")
                padding (12, 6)
                xsize 1120
                ysize 58

                text _cheat_esc(_ct_val) style "cheat_title" xalign 1.0

            if mode == "text":

                grid 10 6:
                    spacing 6

                    for _k in _cheat_pad_keys("text"):
                        use _cheat_key(_k, Function(_cheat_pad_push, target, _k), 106, 50)

            else:

                grid 3 4:
                    spacing 6

                    for _k in _cheat_pad_keys("num"):
                        use _cheat_key(_k, Function(_cheat_pad_push, target, _k), 150, 64)

            hbox:
                spacing 10

                use _cheat_key("退格", Function(_cheat_pad_back, target), 96, 52)
                use _cheat_key("清空", Function(_cheat_pad_clear, target), 96, 52)
                use _cheat_key("取消", Hide("cheat_keypad"), 96, 52)
                use _cheat_key("确定", Function(_cheat_pad_ok, target), 96, 52)

