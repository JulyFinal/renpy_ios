# games/ —— 游戏源码（只放小文件）

这个目录下每个子目录是一个游戏的 `game/` 目录，但**只包含体积小、必须跟代码
一起版本化的那部分**：

```
games/<Game>/game/
    *.rpy / *.rpyc / *.rpymc    脚本
    gui/                        UI 图 + 字体
    tl/                         翻译
    files/                      MilkyTouch 这类把 .rpyc 藏在 files/ 的游戏
    presplash.* icon.*          启动图 / 图标
    script_version.txt
```

**不要**把图片、音频、视频、`*.rpa` 放进来 —— 它们是「外置素材」，由
`tools/make_payload.py` 打成 zip 走 GitHub Release，玩家在 iPad 上解压进 App 的
`Documents/game/`。详见仓库根目录 `README.md`。

## 怎么生成这个目录

```powershell
python tools\sync_game_source.py --game "D:\path\to\<Game>\game" --out games\<Game>\game --clean
```

规则细节见 `tools/sync_game_source.py` 顶部注释。三条要点：

1. 素材类扩展名（图片/音频/视频/`.rpa`）默认不收，但 `gui/`、`tl/`、`files/`
   里的照收（那是 UI 和翻译，不是大素材）；
2. **同名 `.rpyc` 存在时丢弃 `.rpy`** —— `.rpyc` 才是玩家实际运行的字节码；
   压缩版/汉化版里的 `.rpy` 常是 unrpyc 反编译的残次品（MilfyCity 的
   `scripts/rps.rpy:347` 就有 `show paper_selection:` 后跟空块的语法错误）。
   实测 7.4.11 编的 `.rpyc` 在 7.7.3 SDK 下能正常加载；
3. `saves/`、`cache/`、`__pycache__/` 一律跳过。

## 现有游戏

| 目录 | 上游版本 | 文件数 | 体积 | 备注 |
| --- | --- | --- | --- | --- |
| `MilkyTouch/game` | Ren'Py 7.7.3.24061702（`script_version.txt` 写的是 7.4.4） | 132 | 52 MB | 121 个 `.rpyc`（藏在 `files/`）+ 1 个 `Functions.rpyc`，魔数被改成 `RENPY RPC3`（构建时由 `patch_game.py` 改回 RPC2）；素材 2.58GB 全在外置包 |
| `MilfyCity/game` | Ren'Py 7.4.11 | 1492 | 35 MB | 1396 个 `.rpyc`（原版 `.rpy` 是反编译残次品，已丢弃）；1022 个 `.webm` 在素材包里（iOS 播放未验证） |