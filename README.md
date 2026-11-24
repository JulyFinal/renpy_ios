# renpy_ios —— 把 PC 版 Ren'Py 游戏打成 iOS 的未签名 .ipa

用官方 Ren'Py SDK + 官方 renios DLC，在 macOS 上把游戏编成 `.app`，再装进
`Payload/` 打成 `.ipa`，**全程不签名**。产物交给 SideStore / AltStore /
Sideloadly / LiveContainer 自己签。

先说清楚一件事：**iOS 没有真正"免签"这回事**。任何 app 要在 iPhone/iPad 上跑，
都得有一份有效的签名。这里说的"不签名"是指：

* 构建时不需要 Apple 开发者账号、不要证书、不要 provisioning profile（
  `CODE_SIGNING_ALLOWED=NO`），谁都能在 GitHub Actions 上免费跑；
* 装到设备上时，由**你自己**用免费 Apple ID 证书现场签（SideStore / AltStore /
  Sideloadly），或者用 LiveContainer 让多个 app 共用同一份签名。

免费证书 7 天过期，到期重新签一次即可（存档不丢）。

---

## 目录结构

```
scripts/
  zz_ios_patch.rpy     运行期补丁：显示修正 / image_size 容错 / Documents/game* 挂载
  zz_ios_cheat.rpy     金手指：左上角 GM 按钮 → 改数值 / 改对象字段 / 改 persistent / 命令
  patch_game.py        把游戏 game/ 组装成 ios_create 能吃的项目 + 生成构建规则
  fix_project.py       改 Info.plist（文件 App 可见性 / bundle id / 显示名）、清签名配置
  build_ios_ipa.sh     macOS 上：ios_create → xcodebuild → 组 Payload → .ipa
  box_project.py       组装 RenPyBox 通用引擎项目（一个 ipa 装多个游戏）
  box_main_patch.py    改写产物的 base/main.py + 拆 base/game 与 base/picker
tools/
  make_payload.py      把 ipa 里剔除的图片/音频/.rpa 打成外置素材 zip（可多卷）
  pack_game.py         把「仓库脚本 + PC 版素材」拼成 Documents/games/<slug>/（给 box 用）
  sync_game_source.py  从 PC 版游戏目录里挑出「该进 git 的小文件」同步到 games/
box/
  game/zz_box_picker.rpy   RenPyBox 的开局选择器（零素材，只用 Solid + 文字）
games/
  <Game>/game/         游戏脚本 + 字体 + 翻译（几十 MB，进 git）
docs/
  *.png / *.jpg        真机截图（README 里引用）
.github/workflows/
  build-ios.yml        云端打包（macOS runner，mode=game / mode=box）
```

已发布的成品（都在 [Releases](https://github.com/JulyFinal/renpy_ios/releases)）：

| tag | 内容 |
| --- | --- |
| `renpybox-1.0.1` | **通用引擎**：一个 app 装多个游戏，开局选择（推荐） |
| `milkytouch-1.0.1` | MilkyTouch 单独包（不用 box 时用，55MB） |
| `milfyCity-1.0.0` | MilfyCity 单独包（56MB，需自己放素材） |

`renpy_ios` 只放**代码和脚本**。图片/音频/`.rpa` 这些几百 MB 到几 GB 的素材
不进仓库，走「外置素材包」：打成 zip 放到 GitHub Release，你在 iPad 上用
「文件」App 下载解压，拖进 app 的 `Documents/game/`。

为什么这么做：`archive.rpa` 一个文件就 1.3GB，git 管不了；而自签工具对包体积
很敏感。ipa 只有 60MB 左右时，装起来、重签起来都轻松得多。

---

## 一、把游戏脚本放进仓库

在本机（Windows 就行）跑：

```powershell
python tools/sync_game_source.py `
  --game "D:\path\to\MilkyTouch\game" `
  --out  "games\MilkyTouch\game" `
  --clean
```

它会挑出这些进 git：

| 收 | 不收 |
| --- | --- |
| `*.rpy` / `*.rpyc` / `*.rpymc` 脚本 | `*.rpa`（→ 外置素材） |
| `gui/**`（UI 图 + 字体） | `images/**`、`audio/**`、`videos/**`（→ 外置素材） |
| `tl/**`（翻译） | `saves/`、`cache/` |
| `files/**`（MilkyTouch 的 .rpyc 藏在这） | 视频（`.webm/.mp4/...`） |
| `presplash.*`、`icon.*`、字体 | |

还有一条规则：**同名 `.rpyc` 存在时，丢掉那个 `.rpy`**。很多压缩版/汉化版里
的 `.rpy` 是 unrpyc 反编译出来的残次品（MilfyCity 的 `scripts/rps.rpy:347`
就是 `show paper_selection:` 后面跟空块，一编译就报
`show statement expects a non-empty block`），而 `.rpyc` 才是玩家实际跑的
字节码。原版目录里 `.rpyc` 的 mtime 永远比 `.rpy` 新，所以游戏一直用的是
`.rpyc`；两个都留着，git checkout 的 mtime 又不可靠，会随机选中坏源码。

目前仓库里已经有：

* `games/MilkyTouch/game` —— 132 个文件 / 52 MB
* `games/MilfyCity/game` —— 1492 个文件 / 35 MB

---

## 二、打包 ipa

### 方式 A：GitHub Actions（推荐，不用自己有 Mac）

1. push 到 GitHub；
2. 仓库页面 → **Actions** → 左边选 **Build unsigned iOS IPA** → **Run workflow**；
3. 参数：
   * `game`：`MilkyTouch` 或 `MilfyCity`
   * `renpy_version`：`7.7.3`（默认，已验证）
   * `split_assets`：`true`（外置素材，ipa 只有 ~60MB）
   * `display_name`：图标下的名字，例如 `Milky Touch`
   * `bundle_id`：留空则 `com.domain.<Game>`，建议自己定一个，例如
     `com.julyfinal.milkytouch`（重装/升级要靠它认人）
* `assets_tag`：素材 Release 的 tag。**MilfyCity 必填**（原因见下），
     MilkyTouch 留空即可
4. 跑完在 **Artifacts** 里下 `<Game>-ipa-unsigned`，里面有 `.ipa` 和 `.sha256`。

workflow 干的事：下 `renpy-7.7.3-sdk.zip` 和 `renpy-7.7.3-renios.zip`
（renios 是**独立 DLC**，必须解到 `<SDK>/renios`）→ `patch_game.py` → 在 SDK
目录里 `renpy.sh launcher ios_create` → `fix_project.py` → `xcodebuild
CODE_SIGNING_ALLOWED=NO` → 组 `Payload/` 打 zip。

整轮大约 10 分钟（MilkyTouch 完全不下载素材）。

#### 如果 Actions 排不到 macOS runner

GitHub 托管的 macOS runner 不是所有账号都有。两个典型症状：

* 一两秒就 cancelled，注解写
  `The configuration 'macos-14-arm64-us-default' is not supported`；
* 一直 `queued`，`runner_id` 始终是 0，几十分钟都没人领。

两种绕法：

* **自建 runner**：找一台 Mac，装 GitHub Actions runner 并打上标签（例如
  `my-mac`），然后 Run workflow 时把 `runner` 参数填成 `my-mac`；
* **干脆不用 Actions**：直接在任意一台 Mac 上跑方式 B，脚本完全一样。

#### 为什么两个游戏现在都「不用给素材」

MilkyTouch 的脚本全是 `.rpyc`，构建期 Ren'Py 只做字节码转换，**不读任何图片**。

MilfyCity 会在 `init` 里调 `renpy.image_size()`：

```
game/scripts/gui/computer/scenes_gallery/scenes_gallery_setup.rpy:4   MaxScale2()
game/scripts/gui/computer/scenes_gallery/scenes_gallery_images.rpy:4  <- 在 init python 里调用
```

项目里没有 `images/secret_gallery/Scenes/1.png` 就会

```
IOError: Couldn't find file 'images/secret_gallery/Scenes/1.png'.
```

`ios_create` 取不到 dump，整轮失败。**现在这个坑已经用补丁解决了**：
`zz_ios_patch.rpy` 把 `renpy.image_size` 包了一层，**只在文件真的不存在时**
返回占位尺寸 (1920,1080) 并打一行警告，于是纯源码（34.8 MB）就能出 ipa，
CI 也不必下载 1.1 GB 素材。游戏真正跑起来时素材都在，走的是真实尺寸。

想恢复严格行为（缺图就报错）：构建时设 `RENPY_IOS_STRICT_IMAGES=1`。

`build_ios_ipa.sh --media <dir>` 这个开关还留着：极少见的情况下你希望构建期就
用真实尺寸（比如 init 里按图片真实宽高算坐标），可以把 PC 上的素材目录挂进去
（走 `RENPY_IOS_GAME_DIR` → `zz_ios_patch.rpy`）。**这些素材不会进 base/**，
ipa 依然是 51 MB，运行时还是靠设备上的 `Documents/game*/`。

### 方式 B：本地 macOS

```bash
export SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy
python3 scripts/patch_game.py \
    --sdk ~/renpy-7.7.3-sdk \
    --game games/MilkyTouch/game \
    --out  work/MilkyTouch \
    --name MilkyTouch --display-name "Milky Touch" --version 1.0.0

bash scripts/build_ios_ipa.sh \
    --sdk ~/renpy-7.7.3-sdk \
    --project work/MilkyTouch \
    --out dist \
    --display-name "Milky Touch" \
    --bundle-id com.julyfinal.milkytouch
```

MilfyCity 要额外加 `--media /path/to/解压出来的/game`（可以给多个）：

```bash
bash scripts/build_ios_ipa.sh ... \
    --media ~/assets/MilfyCity/game --media ~/assets/MilfyCity/game_part2
```

> `ios_create` / `ios_populate` 本身在 Windows / Linux 上也能跑，只有
> `xcodebuild` 那一步必须 macOS。所以本机上可以先跑到 `work/` + Xcode 工程，
> 再拿到 Mac 上编。

---

## 二·B、一个 ipa 装多个游戏（RenPyBox）

如果你想要「**装一个 app，以后所有游戏都往里加，打开时先选游戏**」，
用 `mode=box` 打一个**通用引擎 ipa**（约 60MB，里面没有任何游戏）：

| 东西 | 放在 iPad 上的位置 |
| --- | --- |
| 引擎本身 | 装一次就行，以后不用重装 |
| 游戏 | `<App>/Documents/games/<slug>/game/…`（每个游戏一个文件夹，随时加/删） |
| 存档 | `<App>/Documents/saves/<slug>/`（每个游戏独立，互不污染） |
| 当前选择 | `<App>/Documents/current_game.txt`（一次性的，读完就删） |

实测效果（iPhone Air / iOS 27.2 / LiveContainer 3.8.14）：

![选择器](docs/renpybox_picker.png)

![进入游戏](docs/renpybox_milkytouch.jpg)

### 怎么打

Actions → **Build unsigned iOS IPA** → Run workflow：

```
mode          = box
display_name  = RenPyBox          # 桌面图标名，随便起
bundle_id     = com.julyfinal.renpybox
runner        = macos-15
```

也可以本地 macOS 打：

```bash
python3 scripts/box_project.py \
    --repo "$PWD" --sdk ~/renpy-7.7.3-sdk --out work/RenPyBox --clean

bash scripts/build_ios_ipa.sh \
    --sdk ~/renpy-7.7.3-sdk \
    --project work/RenPyBox \
    --out dist --display-name "RenPyBox" \
    --bundle-id com.julyfinal.renpybox \
    --box
```

### 怎么往 iPad 里加游戏

1. 在本机把「仓库里的脚本」和「PC 版的大素材」拼成一个游戏目录：

   ```powershell
   python tools\pack_game.py `
     --slug milkytouch --title "MilkyTouch" `
     --repo-game "games\MilkyTouch\game" `
     --media     "D:\path\to\MilkyTouch\MilkyTouch\game" `
     --out       "dist\games"
   ```

   产出 `dist\games\milkytouch\`，里面是 `title.txt` + `game/`。
2. 把这个文件夹（整个 `milkytouch`，不是里面的 `game`）放到
   `<App>/Documents/games/` 下。Windows 上用 Apple Devices / iTunes 的
   「文件共享」直接拖，macOS 用 Finder 的「文件」，或者用 USB 工具（本仓库
   调试时用的是 `pymobiledevice3` 的 AFC）。
3. 打开 app → 选择器里点这个游戏 → **直接进游戏**，不用退出再点一次。

> **换游戏不用杀 App**：选择器点游戏时调用 `renpy.utter_restart()`
> （不是 `renpy.quit()`）。它会抛 `UtterRestartException`，被
> `renpy/bootstrap.py:366-371` 接住 → `renpy.reload_all()` → 重新跑
> `renpy.main.main()`：重新读 `current_game.txt`、重算 searchpath、重新枚举脚本。
> 整个过程在同一个进程里完成，用户看到的就是「点一下 → 进入游戏」。
>
> 进游戏后**右上角**有一个半透明 `<< GAMES` 小按钮（`config.overlay_screens`
> 挂的 `renpybox_home` 屏），点它会不写选择文件直接重启，回到选择器。
> 这个按钮在真机上是**实验性**的（有的游戏右上角 UI 会压住它），不用也没关系——
> 退出 App 再打开本来就会回到选择器。

早期版本是「写文件 → `renpy.quit()` → 用户再点图标」，已经不需要了。

### 它是怎么实现的

只改了一个文件：`base/main.py`（`scripts/box_main_patch.py` 注入）。
Ren'Py 引擎只通过 `renpy.__main__` 的这两个函数取路径（见
`renpy/main.py:350-351` 和 `:473`）：

* `predefined_searchpath(commondir)` → 决定这次启动加载哪套脚本；
* `path_to_saves(gamedir)` → 决定存档写哪里。

所以 box 包的 `base/` 被拆成：

```
base/game/     只放 zz_ios_patch.rpyc / zz_ios_build.rpyc / zz_ios_cheat.rpyc（两个模式下都要加载）
base/picker/   选择器（zz_box_picker.rpyc + 中文字体 SourceHanSansLite.ttf）
```

`base/game` 永远在 searchpath 里，所以显示修正、`image_size` 容错对每个游戏都生效。

启动/切换时序（`renpy/bootstrap.py:330-391` 的 `while` 循环）：

1. `renpy.main.main()` → `config.init()` → 调我们的 `predefined_searchpath()`
   （在这里读 `current_game.txt` 并立刻删掉，所以它是「一次性」的）；
2. 按 searchpath **枚举并加载脚本** —— 这一步在 init 代码**之前**，
   所以游戏跑起来之后没法原地换一套脚本；
3. 跑 init 代码 → 主循环；
4. 选择器里点游戏 → 写 `current_game.txt` → `renpy.utter_restart()`
   → 抛 `UtterRestartException` → bootstrap 接住 → `renpy.reload_all()`
   → **回到第 1 步**（同一进程，App 不退出）。

⚠️ 第 1 步执行的是 `base/main.py`，它跑在 Ren'Py 自带的 **Python 2.7** 上。
注入的代码里有中文注释，所以第一行**必须**是 `# -*- coding: utf-8 -*-`，
否则 py2 直接 `SyntaxError` → 「启动瞬间全黑、零日志」（坑 13）。
`scripts/box_main_patch.py` 的 `ensure_utf8_decl()` 会自动补。同理，注入代码
本身也要保持 **py2 兼容**（不能用 f-string、`pathlib`、`print(..., file=)` 之外
的 py3 特性时小心）。

---

## 二·C、金手指（左上角 GM 按钮）

打包时会自动带上 `scripts/zz_ios_cheat.rpy`（`patch_game.py` 的 `--no-cheat` 可关，
RenPyBox 模式由 `box_project.py` 打进工程，再由 `box_main_patch.py` 的 `KEEP_IN_GAME`
留在 `base/game/` —— 放进 `base/picker/` 的话游戏启动后根本加载不到）。游戏里左上角常驻一个
半透明 **GM** 按钮，点一下弹出全屏面板，四个页签：

| 页签 | 干什么 |
| --- | --- |
| 数值 | 列出 store 里所有 `int` / `float`（money、day、好感度……）。`-` / `+` 按步长加减，`改` 精确输入 |
| 对象 | store 里的自定义对象（例如 MilfyCity 的 `inventory`），点 `进入` 改它的数字字段，`← 返回` 回上一级 |
| 持久 | `persistent` 里的数字和 True/False 开关（章节、已解锁的 CG 之类），整局游戏都生效 |
| 命令 | 输入 Python 表达式/语句直接作用于 store，等价于控制台：`money = 99999`、`inventory.money += 5000` |

操作要点：

* 步长按钮 `1 / 10 / 100 / 1k / 10k / 100k` 管 `-` `+` 一次加多少；
* 顶部有筛选框，名字多的游戏直接打字过滤；框旁边的小键盘是给没有实体键盘的
  触屏用的（文本框里点一下会弹系统输入法，两种都行）；
* 改完立刻生效，`关闭` 收起面板。**改坏了就返回主菜单读档**，所以建议改之前先存一次档；
* 引擎自己的控制台（`00console.rpy`）在手机上没法用——它靠 `Esc`/右键退出，而且
  `zz_ios_patch.rpy` 为了手机端干净把 `config.developer` 关掉了，所以才另写了这个。

实现上要注意的两点（改这个文件前先看）：

* 枚举 store 时**不能**用 `isinstance(k, str)` 判断键：Ren'Py 把 store 里的 `str`
  重绑成了 `unicode`，`persistent` 字段和对象属性都是字节串键（`default` 语句建的变量
  才是 unicode 键），一用就整页空白；代码里用 `basestring` 兜住。
* 所有动态文本都要过 `_cheat_esc()`：Ren'Py 会把 `[` 当插值起点、`{` 当文本标签，
  文本键盘输入一个 `[` 就会抛 `ends with an open format operation`。

## 三、生成外置素材包（本机跑，一次性）

```powershell
python tools\make_payload.py `
  --game "D:\path\to\MilkyTouch\game" `
  --out  dist\payload
```

产出：

```
dist/payload/assets.part1.zip   ->  解压出 game/          （archive.rpa，约 1.3GB）
dist/payload/assets.part2.zip   ->  解压出 game_part2/    （audio + images，约 1.3GB）
dist/payload/assets-manifest.json
```

为什么分卷：**GitHub Release 单个附件上限 2 GiB**，而 MilkyTouch 的素材有
2.58GB。也不能用 `.tar.zst` —— iPad 的「文件」App 只认 `.zip`。

为什么每卷用不同的顶层目录：iOS 上合并两个同名目录极其难操作。`part1` 解出
`game/`，`part2` 解出 `game_part2/`，两者**并排放在 Documents 下**即可，
`zz_ios_patch.rpy` 会把 `Documents` 下所有以 `game` 开头的目录都加进 searchpath。

然后把 `dist/payload/*.zip` 上传到 GitHub Release（随便一个 tag，比如
`assets-MilkyTouch`）。

---

## 四、装到 iPhone / iPad 上

### 4.1 安装 ipa

任选一个：

* **SideStore**（推荐，设备上直接签，7 天自动续签）
* **AltStore**（同上，需要电脑跑 AltServer）
* **Sideloadly /爱思**（电脑上签好再装）
* **LiveContainer**（一份签名装多个 app，适合同时装两个游戏）

因为 ipa 是未签名的，直接双击装是不行的，必须过这些工具。

已经打好的包放在 Release：

* `milkytouch-1.0.1` → `MilkyTouch.ipa`（58 MB，不含素材，含显示兜底补丁）
* `milkytouch-1.0.0` → 首个可用版本（同样不含素材，但没有横屏兜底）
* `milfyCity-1.0.0` → `MilfyCity.ipa`（56 MB，不含素材；素材用 PC 版 `game/` 里的媒体文件）
* `milkytouch-diag1` / `diag2` → 排查显示问题时的诊断包，可以忽略

**LiveContainer 用户必须先看 4.1.2**（不改朝向锁，画面只会显示左上角一条）。

### 4.1.1 放素材的另一种办法（比走网络快）

`UIFileSharingEnabled` 打开之后，用数据线接电脑：

* **Finder**（macOS 10.15+）：选设备 → 文件 → 找到 app → 直接把 `game`
  文件夹拖进去；
* **Windows**：装 Apple Devices 或 iTunes，同样在「文件共享」里拖；
* **SideStore/AltStore 安装的 app 都支持这个**；LiveContainer 里的 app
  数据在 LiveContainer 自己的容器里，Finder 看不到，得走 4.2 的 zip 路线。

### 4.1.2 LiveContainer 用户必读：把这个 app 的「朝向锁」改成横屏

**这是唯一必须手动改的 LiveContainer 设置，不改就会「只有左上角一条画面」。**

LiveContainer → 长按 MilkyTouch / MilfyCity → Settings（齿轮）→
**Orientation Lock / 朝向锁** → 选 **Landscape（横屏）** → 关掉 app 重新打开。

原因（详见坑 12）：Ren'Py 的 iOS 后端是 SDL2，它建窗口时要问系统「现在是不是横屏」。
LiveContainer 默认 `LCOrientationLock = Disabled`，此时它没有把宿主的 scene 朝向
改掉，SDL 拿到的窗口是竖屏 420x912 点（帧缓冲 1260x2736），而屏幕是横屏
2736x1260 —— 于是 glViewport 只覆盖屏幕左上角一条 1260x246 的带子。

设成 Landscape 后 LiveContainer 会 swizzle
`UIViewController.__supportedInterfaceOrientations` 等三个方法并强制
`interfaceOrientation = UIInterfaceOrientationLandscapeRight`，SDL 立刻拿到
横屏 912x420 点 / 2736x1260 像素，`drawable_viewport = (249, 0, 2238, 1260)`，
画面正常铺满（1920x1080 内容等比缩放，左右各 249 像素黑边，正常现象）。

用 SideStore / AltStore / Sideloadly 装的不需要这一步（app 用自己 plist 里
声明的横屏方向）。

设好之后应该是这样（iPhone Air，2736x1260 屏幕，1920x1080 内容等比铺满高度，
左右各 249 像素黑边，属正常）：

![MilkyTouch 横屏正常显示](docs/milky_fixed.png)

### 4.2 放素材

1. 在 iPad 上把 Release 里的 `assets.part1.zip`、`assets.part2.zip` 下载下来
   （「文件」App 里点 zip → 自动解压成同名文件夹）；
2. 打开「文件」App → **我的 iPad**（或"我的 iPhone"）→ 找到游戏名字的目录
   （就是 app 的 Documents，名字等于 app 的显示名）；
3. 把解压出来的 `game` 和 `game_part2` 两个文件夹整个拖进去；
4. 启动游戏。

第一次启动时看日志应该能看到：

```
[renpy-ios] external game dir: /var/mobile/Containers/.../Documents/game, .../Documents/game_part2
[renpy-ios] external archives: archive
```

看不到这两行、或者游戏黑屏，多半是素材没放对位置（见下面 FAQ）。

`UIFileSharingEnabled` + `LSSupportsOpeningDocumentsInPlace` 是
`fix_project.py` 写进 Info.plist 的，没有这两个开关，「文件」App 里根本看不到
app 的 Documents。

---

## 五、已知坑（都是踩过的）

### 1. `.rpyc` 魔数被改成 `RENPY RPC3`

有些"整合版/反破解版"游戏把 `renpy/script.py` 里的
`RPYC2_HEADER = b"RENPY RPC2"` 改成了 `RENPY RPC3`（常量名不变，只换字面量，
目的是让 unrpyc 解析失败）。官方 SDK 只认 RPC2，于是报：

```
Exception: Could not load file .../game/files/Characters.rpyc
```

`patch_game.py` 里的 `normalize_rpyc_headers()` 会把每个 `.rpyc` 前 10 个字节
改回 RPC2。**因为字节码载荷本身没变**（MilkyTouch 自带的 `renpy/script.py` 和
官方 7.7.3 的逐字节只差这一行），改头是安全的。

### 2. `config.name` 被游戏自己覆盖

`ios_create` 用 dump 出来的 `config.name` 当 Xcode **target 名和 PRODUCT_NAME**。
MilkyTouch 自己在 `options.rpyc` 里写 `config.name = "Milky Touch"`（带空格），
会让 `xcodebuild -target` 很难写。

解：`zz_ios_build.rpy` 里在 `init 999` 再设一次（main.py 是在 init 代码跑完后
才调 `renpy.dump.dump()`，所以 999 仍然生效），目标名统一成干净的 ASCII。

### 3. 游戏自带的 `.rpa` 默认**会**被打进包

`renpy/common/00build.rpy` 里那条 `("**.rpa", None)` 属于 `renpy_patterns`，
只作用于 SDK 自己的 `renpy/` 目录，**不作用于游戏 `game/` 里的 .rpa**。实测
MilkyTouch 的 1.32GB `archive.rpa` 原样进了 `base/`。split 模式必须自己

```python
build.classify("**.rpa", None)
```

（已经在 `zz_ios_build.rpy` 模板里了。）

### 4. `xcodebuild` 只能用 `-target`，不能 `-scheme`

renios 生成的 `prototype.xcodeproj` 里**只有 project.pbxproj，没有任何 shared
scheme**。`-scheme` 一定失败。

### 5. SDK 版本和游戏不一致

MilkyTouch 是 7.7.3.24061702 打包的，但 `script_version.txt` 写的是 `(7,4,4)`。
`patch_game.py` 会警告但不拦。至今实测能跑；真报字节码错误的话，换对应版本的
SDK（`renpy_version` 参数）再试。

### 6. `.webm` 视频

renios 的 prototype 里带了完整 ffmpeg 静态库（libavformat/libavcodec/...），
所以 Ren'Py 自己的播放器**未必**放不了 webm。但这一点**没有实测过**。
MilfyCity 有 1022 个 `.webm`，真机上如果视频黑屏，优先怀疑这里。

### 7. 中文 / 字体

中文字体在 `game/gui/fonts/`（MilkyTouch 的 `TCM.TTF`/`TCB.TTF` 各 9.3MB），
属于"留在 ipa 里"的保留项。如果启动后满屏方块，说明字体没进包 —— 检查
`zz_ios_build.rpy` 里 `game/gui/**` 那条保留规则有没有被后面的排除规则抢先命中
（`build.classify` 是**首条命中生效**）。

### 8. 有的游戏在 `init` 里就读图片

MilfyCity 的 `scripts/gui/computer/scenes_gallery/scenes_gallery_setup.rpy` 定义了
`MaxScale2()`，而 `scenes_gallery_images.rpy:4` 在 `init python` 里对一堆图片调它。
构建项目里没有那些图，`renpy.image_size()` 直接抛 `IOError`，`ios_create` 因此
拿不到 dump（报错是好几步之外的 `Launching the project failed.` + `error: Invalid
window`，真实原因藏在子进程输出里，见坑 9）。以前要用 `--media` 把素材塞进去，
现在不用了。

**现在的解法**：`zz_ios_patch.rpy` 在 `init -2000` 把 `renpy.image_size` 包了一层，
**只在文件真的不存在时**返回占位尺寸 `(1920, 1080)` 并打一行
`[renpy-ios] image_size fallback ...` 警告。构建期缺图不再是致命错误，纯源码
（MilfyCity 只有 34.8 MB）就能出 ipa；游戏真正跑起来时素材都在，走真实尺寸。

想恢复严格行为：构建时设 `RENPY_IOS_STRICT_IMAGES=1`。真需要构建期就用真实
尺寸时，`build_ios_ipa.sh --media <dir>` 仍然可用（走 `RENPY_IOS_GAME_DIR`）。

### 9. `ios_create` 失败时的报错会骗人

真实报错在 launcher 弹出的错误对话框里，而 dummy 视频驱动画不出对话框，
于是只剩一句

```
error: Invalid window
```

真正的原因要自己重跑子进程才看得见：

```bash
cd "$SDK" && SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./renpy.sh <PROJECT> quit
```

（`renpy.sh` 在 macOS 上，Windows 上换成 `renpy.exe`。）

### 10. `ld: library 'python3.9' not found`

renios 自带的 `prototype.xcodeproj` 里，Debug 配置写的是 `-lpython2.7`，
Release 配置却写成 `-lpython3.9`，而 `prototype/prebuilt/{release,debug}/`
里只有 `libpython2.7.a`（Ren'Py 7.x 是 Python 2.7）。所以 Release 链接必挂。

`fix_project.py` 已经在处理：它扫 `prebuilt/release` 里真实存在的
`libpythonX.Y.a`，把 pbxproj 里所有 `-lpythonX.Y` 统一成那个名字。

### 11. `The Xcode project already exists. Would you like to rename...`

`ios_create` 的目标目录只要已存在就会问这句话，无头环境里 `input()` 直接
`EOFError`。所以 `build_ios_ipa.sh` 里 `rm -rf dist/xcode` 之后**不能**再
`mkdir dist/xcode`——让 `ios_create` 自己建。

### 12. iOS 上画面挤在左上角 / 只看到左侧一条（LiveContainer）

症状：在 LiveContainer 里启动游戏，画面内容只出现在**左上角**（或左侧约 45%），
其余全黑；但游戏是活的，按钮点得到。

真因（一路查下来的完整链条，**不要**再往 Ren'Py 的数字上找问题）：

1. Ren'Py 的 iOS 显示后端是 SDL2。`gl2draw.pyx` 用
   `pygame.display.set_mode((0,0), WINDOW_FULLSCREEN_DESKTOP|...)` 建窗口；
2. SDL 的 `UIKit_CreateWindow` 注释写明 "ignore the size user requested, and make
   a fullscreen window"，真正的尺寸来自
   `SDL_uikitvideo.m: UIKit_ComputeViewFrame()`：
   `frame = screen.bounds`，`landscape = IsLandscape(statusBarOrientation) ||
   !(supported_orientations & (Portrait|PortraitUpsideDown))`，
   只有 `fullscreen && (landscape != (frame 宽 > 高))` 时才交换宽高；
3. `UIKit_GetSupportedOrientations()`（`SDL_uikitwindow.m:418-481`）先取
   `validOrientations`（app delegate 的 `application:supportedInterfaceOrientationsForWindow:`
   或主 bundle 的 plist），再读 hint `SDL_IOS_ORIENTATIONS`，最后
   **`if ((valid & mask) == 0) mask = valid`** —— 交集为空就回退成 app 支持的；
4. iOS 27 上 `UIApplication.statusBarOrientation` 已废弃且恒为 portrait；
   LiveContainer 默认 `LCOrientationLock = Disabled` 时，宿主 scene 是竖屏 →
   `frame` 是竖屏 420x912 点，`landscape = false` → 不交换 → 窗口/帧缓冲是
   1260x2736（竖屏）；
5. Ren'Py 按 `(420, 912)` 算布局：`ratio = min(420/1920, 912/1080)`，
   `physical_box = (0, 338, 420, 236)`，`draw_per_phys = 1260/420 = 3`，
   于是 `glViewport(0, 1014, 1260, 708)` —— 只覆盖屏幕 y=1014..1260 一条
   1260x246 的带子，正是肉眼看到的「左上角一条」。

实测数据（`zz_ios_probe.rpy` 写到 `Documents/iosdiag_log.txt`）：

```
# 坏的时候：raw 值是竖屏
raw.pg_get_size = (420, 912)      raw.pg_drawable = (1260, 2736)
draw.physical_box = (0.0, 338.0, 420, 236)
draw.drawable_viewport = (0.0, 1014.0, 1260.0, 708.0)

# 修好之后：SDL 自己就是横屏
raw.pg_get_size = (912, 420)      raw.pg_drawable = (2736, 1260)
draw.physical_box = (83.0, 0.0, 746, 420)
draw.drawable_viewport = (249.0, 0.0, 2238.0, 1260.0)   # 2736x1260 屏幕里铺满高度
```

修法：**把 LiveContainer 里这个 app 的 Orientation Lock 设成 Landscape**
（见 4.1.2）。也可以直接改装置上的
`Documents/Applications/<bundleid>.app/LCAppInfo.plist` 的
`LCOrientationLock`（枚举：`Disabled = 0`、`Landscape = 1`、`Portrait = 2`，
见 LiveContainer 源码 `LiveContainerSwiftUI/Models/LCAppInfo.h`；
`TweakLoader/UIKit+GuestHooks.m` 的 constructor 会读它并 swizzle
`__supportedInterfaceOrientations` / `shouldAutorotateToInterfaceOrientation:` /
`UIWindow setAutorotates:forceUpdateInterfaceOrientation:`，以及
`FBSSceneParameters initWithXPCDictionary:` 里强制
`settings.interfaceOrientation`）。

`zz_ios_patch.rpy` 里另外做了两层**兜底**（在 LC 设置正确时都不触发）：
设 `os.environ["SDL_IOS_ORIENTATIONS"] = "LandscapeLeft LandscapeRight"`
（可用 `RENPY_IOS_ORIENTATIONS` 覆盖，`none` 关闭），以及把
`pygame_sdl2.display.get_size` / `get_drawable_size` 在「上报竖屏」时交换宽高。
兜底只能把画面从「只露左上角一条」改善成「露出左侧 45%」，**根治仍然靠朝向锁**。

### 13. RenPyBox 启动全黑、没有任何日志 —— `base/main.py` 缺 UTF-8 编码声明

症状极其误导：点图标后**整屏全黑**，没有 `log.txt`、没有 `renpybox_log.txt`、
没有 `base/game/cache/`、也没有崩溃报告，看起来像容器/渲染问题。真相是：

`base/main.py` 由 Ren'Py 内嵌的 **Python 2.7** 执行，而 `scripts/box_main_patch.py`
注入的 bootstrap 里有中文注释。按 PEP 263，**没有 coding 声明时 py2 遇到非 ASCII
字节直接报错**，也就是脚本在 App 启动的瞬间就解析失败：

```
SyntaxError: Non-ASCII character '\xe4' in file .../base/main.py on line 1,
but no encoding declared; see http://python.org/dev/peps/pep-0263/
```

修法：`base/main.py` **第一行**必须是 `# -*- coding: utf-8 -*-`。
`scripts/box_main_patch.py` 的 `ensure_utf8_decl()` 会无条件补上（幂等）。

> 排查陷阱：`compile(bytes)`、`py_compile.compile()` **都不会**报这个错，
> 只有真正「把文件当脚本执行」才会。用 SDK 自带的 py2
> （`lib/py2-windows-x86_64/python.exe`）跑一次脚本文件才是可靠判据。

### 14. 搬进盒子的存档「看不见」——页号 + auto 页

用户把 PC 的 `game/saves/` 整个搬进 `Documents/saves/<slug>/` 之后，打开
「加载」却一片空白。这不是存档没读到（引擎侧 `renpy.list_saved_games()`
能列出来），而是**界面显示的位置对不上**，有两个独立原因：

**① 页号停在空页。** 当前存档页号存在 `persistent._file_page` 里，
玩家在 PC 版最后一次存/读停在第 6 页，这个页号会跟着 `persistent` 一起搬过来。
而每页格子数是 `gui.file_slot_cols * gui.file_slot_rows`（MilkyTouch 3×2=6，
MilfyCity 2×2=4），第 6 页的槽名是 `6-1`…`6-6`，这些槽根本不存在 → 整页空白。

槽名规则见 `renpy/common/00action_file.rpy:134 __slotname()`：
`name = str(page) + "-" + str(slot)`，磁盘文件名就是 `<page>-<slot>-LT1.save`。

修法（已写进 `scripts/zz_ios_patch.rpy` 的 0.8 节，`init 997`）：
启动时若当前页一个存档都没有，就自动跳到第一个有存档的页。
只在 `RENPY_IOS_BOX=1` 时生效，auto / quick 这类非数字页不动。

**② PC 存档几乎都是 `auto-N` 自动存档。** `auto-1-LT1.save` 只对应加载
界面的 **A（自动存档）页**，普通页 1、2、3… 里永远没有它的格子。
所以原样搬过来，玩家在主界面看到的就是「没有存档」。

修法：用 `tools/import_saves.py` 把 `auto-*` / `quick-*` / `_reload-*`
按时间从新到旧重新编号成普通页槽：

```bash
python tools/import_saves.py \
    --saves "C:/path/to/Game/game/saves" \
    --out   "_stage/saves/milfyCity" \
    --per-page 4          # = gui.file_slot_cols * gui.file_slot_rows
```

它还会跳过引擎大版本比盒子新的存档（8.x 的档在 7.x 上读不了，摆出来点了就报错），
默认不动 `persistent`（画廊/音乐解锁），需要时加 `--persistent`。

### 15. 进游戏「卡一下然后直接退出」——缺 `gui/window_icon.png`

第一次 interact 时 Ren'Py 会走 `renpy/display/core.py:1080 post_init()` → `set_icon()`
（`set_icon` 本体在 `renpy/display/core.py:1113`），里面 `renpy.loader.load(config.window_icon)`。
`config.window_icon` 在 `renpy/config.py:43` 的默认值是 `None`，但几乎所有游戏的 `gui.rpy`
都会 define 成 `"gui/window_icon.png"`；而 `set_icon` 里那个 `try` 只吞
`renpy.webloader.DownloadNeeded`，文件不存在时 `IOError` 会一路冒到 script 层：

```
IOError: Couldn't find file 'gui/window_icon.png'.
```

表现就是启动画面刚起来（`splashscreen` 里第一个 `renpy.pause`）就退出，游戏目录留下一份
`traceback.txt`，设备上**不一定**有 .ips 崩溃报告——进程其实是正常退出的。两种常见起因：

* PC 压缩版 / 手游移植版把 `gui/window_icon.png` 删了（它只对桌面窗口图标有意义）；
* 拷游戏时目录层级错了，比如文件实际在 `game/gui/gui/window_icon.png`。

修法（已写进 `scripts/zz_ios_patch.rpy` 的 0.65 节，`init -1940`）：包一层
`Interface.set_icon`，加载失败就打一行 `[renpy-ios] window_icon missing, skipped`
并当作没有图标（iOS 本来也不显示窗口图标）。本地 A/B 验过：去掉守卫必崩，带上守卫正常进游戏。

---
## 六、这套流程的核心机制（改代码前请先读）

Ren'Py 的 loader（`renpy/loader.py`）：

* `transfn(name)` 对 `config.searchpath` 每一项做
  `os.path.join(config.basedir, d, name)`。`d` 是绝对路径时 `os.path.join`
  会丢掉 `basedir`，**所以绝对路径能直接生效**；
* `load_from_archive()` 里是 `afn = transfn(prefix)`，所以
  `config.archives` 里只能放**相对 basename**（`"archive"`），不能塞绝对路径；
* `main.py` 在 init 代码跑完后（约 :604）会**再调一次** `index_archives()`，
  注释写着 "because the list of known archives may have changed" ——
  我们在 `init -2000 python` 里改 `config.archives` 是官方支持的时机；
* iOS 上 `config.savedir` 由 `renpy.py:path_to_saves()` 返回
  `NSSearchPathDirectory.NSDocumentDirectory`，也就是
  `<App 容器>/Documents`，正好是「文件」App 能看见的那层。

`build.classify()` 的规则是**先追加先命中**，dump 出来的顺序是
`early_base_patterns + base_patterns + late_base_patterns`，最后一条是
`("**", "all")`。所以「保留 `game/gui/**`」必须写在「排除 `**.png`」之前，
否则 UI 图会被一起踢出去。而 `zz_ios_build.rpy` 用 `init -1400`，是为了让这些
规则排在游戏自己 `options.rpy`（`init 0`）之前。

`ios_populate` 是用 `noarchive=True` 调 `Distributor` 的，**不会生成任何 .rpa**，
所有东西都是散文件写进 `base/`。`base/` 在 pbxproj 里是一个 folder reference
（`lastKnownFileType = folder`），会被原样拷进 `<App>.app/base/`。

---

## 七、换一个新游戏

1. `python tools/sync_game_source.py --game <PC 版 game 目录> --out games/<New>/game --clean`
2. 试跑一次 `ios_create`（或直接跑 Actions）。如果报
   `Couldn't find file 'images/...'`，说明这游戏在 `init` 里就读图（坑 8），
   那么 CI 需要 `assets_tag`：
3. `python tools/make_payload.py --game <PC 版 game 目录> --out dist/payload`
4. 素材 zip 传 Release（tag 例如 `assets-<New>`），ipa 走 Actions
   （`game` 下拉框里加一项，或在 workflow_dispatch 里手填）。
5. 如果游戏用 1920×1080 之类的固定像素坐标、且没有做手机适配，画面可能被裁切
   —— 那是游戏本身的问题，不是打包流程的问题。