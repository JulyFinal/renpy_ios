#!/bin/bash
# =============================================================================
# build_ios_ipa.sh —— 在 macOS 上把一个已组装好的 Ren'Py 项目打成**未签名** .ipa
#
# 为什么必须在 macOS 上跑：
#   ios_create / ios_populate（Windows、Linux 也能跑）只负责生成 Xcode 工程和 base/ 目录；
#   真正把 .app 编译出来要靠 xcodebuild，只有 macOS 有。
#
# 为什么不用 `renpy.sh distribute --package ios`：
#   那是 6.x 时代的入口。7.x 的 iOS 打包入口只有 launcher 注册的两个命令：
#       renpy.sh launcher ios_create   <project> <dest>
#       renpy.sh launcher ios_populate <project> <dest>
#   （见 $SDK/launcher/game/ios.rpy 里 register_command 的部分）
#
# 前置：
#   * $SDK 是 Ren'Py SDK 根目录，且 $SDK/renios 存在
#     （renios 是独立 DLC：https://www.renpy.org/dl/<ver>/renpy-<ver>-renios.zip）
#   * $PROJECT 已经由 scripts/patch_game.py 组装好（含 game/ 与 zz_ios_patch.rpy）
#
# 用法：
#   ./build_ios_ipa.sh --sdk /path/renpy-7.7.3-sdk --project /path/work/MyGame \
#       --out /path/dist --display-name "My Game" --bundle-id com.me.mygame --version 1.0.0
#
#   --media <dir>   （可重复）构建期才需要的素材目录。有些游戏在 init 里就调
#                   renpy.image_size()（MilfyCity 的 MaxScale2），项目里必须有图
#                   才能启动；但它们不进 ipa，只是让 ios_create 阶段的 dump 能过。
#                   这几个目录会以 RENPY_IOS_GAME_DIR 传给 Ren'Py，最终仍然靠
#                   iPad 上 Documents/game*/ 提供。
#
# 产出：
#   <out>/<Name>.ipa        未签名 ipa（Payload/<Product>.app）
#   <out>/<Name>.ipa.sha256
# =============================================================================

set -euo pipefail

SDK=""
PROJECT=""
OUT="dist"
DISPLAY_NAME=""
BUNDLE_ID=""
VERSION="1.0.0"
BUILD_NUMBER="1"
MEDIA=""
KEEP_XCODE_BUILD="0"

log() { printf '\033[1;36m[build_ipa]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[build_ipa] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --sdk)          SDK="$2"; shift 2 ;;
        --project)      PROJECT="$2"; shift 2 ;;
        --out)          OUT="$2"; shift 2 ;;
        --display-name) DISPLAY_NAME="$2"; shift 2 ;;
        --bundle-id)    BUNDLE_ID="$2"; shift 2 ;;
        --version)      VERSION="$2"; shift 2 ;;
        --build-number) BUILD_NUMBER="$2"; shift 2 ;;
        --media)        MEDIA="${MEDIA:+$MEDIA:}$2"; shift 2 ;;
        --keep-xcode-build) KEEP_XCODE_BUILD="1"; shift ;;
        -h|--help)      sed -n '2,40p' "$0"; exit 0 ;;
        *)              die "unknown argument: $1" ;;
    esac
done

[ -n "$SDK" ]     || die "--sdk is required"
[ -n "$PROJECT" ] || die "--project is required"
[ "$(uname -s)" = "Darwin" ] || die "this script needs macOS (xcodebuild)"

SDK="$(cd "$SDK" && pwd)"
PROJECT="$(cd "$PROJECT" && pwd)"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"

[ -d "$SDK/renpy" ]  || die "$SDK does not look like a Ren'Py SDK"
[ -d "$SDK/renios" ] || die "$SDK/renios is missing; unpack renpy-<ver>-renios.zip into the SDK root"
[ -d "$PROJECT/game" ] || die "$PROJECT/game is missing; run scripts/patch_game.py first"

XCODE_OUT="$OUT/xcode"
BUILD_DIR="$OUT/xcode-build"
rm -rf "$XCODE_OUT" "$BUILD_DIR"
# 只能建 BUILD_DIR。$XCODE_OUT 千万不能提前 mkdir：ios.rpy:142 的逻辑是
# "目标目录已存在 → 问你要不要重命名旧工程"，无头环境里 input() 直接
# EOFError，整步就挂了。
mkdir -p "$BUILD_DIR"

# -----------------------------------------------------------------------------
# 1) ios_create：生成 Xcode 工程 + base/（Ren'Py 运行时 + 游戏脚本）
# -----------------------------------------------------------------------------
# 注意：launcher 会按「当前工作目录」去找 launcher/ 项目，所以必须先 cd 进 SDK。
log "ios_create -> $XCODE_OUT"
(
    cd "$SDK"
    export SDL_VIDEODRIVER=dummy
    export SDL_AUDIODRIVER=dummy
    # 有些游戏在 init 阶段就调 renpy.image_size()（例如 MilfyCity 的
    # scenes_gallery_setup.rpy:MaxScale2），项目里没有图片会直接启动失败，
    # ios_create 也就拿不到 dump。用 RENPY_IOS_GAME_DIR 把外置素材目录临时
    # 挂进 searchpath（zz_ios_patch.rpy 会读这个变量），dump 完 base/ 里依然
    # 不会有这些素材 —— 它们在 base/ 之外，只是构建期可见。
    if [ -n "$MEDIA" ]; then
        export RENPY_IOS_GAME_DIR="$MEDIA"
        log "build-time media: $MEDIA"
    fi
    ./renpy.sh launcher ios_create "$PROJECT" "$XCODE_OUT"
)

[ -d "$XCODE_OUT/base" ] || die "ios_create produced no base/ directory"

# -----------------------------------------------------------------------------
# 2) fix_project：改 Info.plist（文件 App 可见性 / bundle id / 显示名）
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"

ENGINE_NAME="$(basename "$PROJECT")"
[ -n "$DISPLAY_NAME" ] || DISPLAY_NAME="$ENGINE_NAME"
[ -n "$BUNDLE_ID" ]    || BUNDLE_ID="com.domain.$(echo "$ENGINE_NAME" | tr -cd 'A-Za-z0-9')"

log "fix_project (display=$DISPLAY_NAME bundle=$BUNDLE_ID)"
"$PY" "$SCRIPT_DIR/fix_project.py" \
    --project "$XCODE_OUT" \
    --display-name "$DISPLAY_NAME" \
    --bundle-id "$BUNDLE_ID" \
    --version "$VERSION" \
    --build-number "$BUILD_NUMBER"

XCODEPROJ="$(ls -d "$XCODE_OUT"/*.xcodeproj | head -n 1)"
TARGET="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["target"])' "$XCODE_OUT/ios-build.json")"
APP_NAME="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["app_name"])' "$XCODE_OUT/ios-build.json")"

log "xcodebuild: xcodeproj=$(basename "$XCODEPROJ") target=$TARGET"

# -----------------------------------------------------------------------------
# 3) xcodebuild：无签名 Release 构建
# -----------------------------------------------------------------------------
# 关键点：
#   * prototype.xcodeproj 里**没有任何 scheme**，所以只能用 -target，不能用 -scheme。
#   * CODE_SIGNING_ALLOWED=NO 是唯一能让没有证书的机器编出 .app 的开关；
#     顺带把 CODE_SIGN_ENTITLEMENTS 清空，避免 entitlement 校验失败。
xcodebuild \
    -project "$XCODEPROJ" \
    -target "$TARGET" \
    -configuration Release \
    -sdk iphoneos \
    ARCHS=arm64 \
    ONLY_ACTIVE_ARCH=NO \
    CODE_SIGNING_ALLOWED=NO \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGN_IDENTITY="" \
    "CODE_SIGN_IDENTITY[sdk=iphoneos*]=" \
    CODE_SIGN_ENTITLEMENTS="" \
    ENABLE_BITCODE=NO \
    VALIDATE_PRODUCT=NO \
    CONFIGURATION_BUILD_DIR="$BUILD_DIR" \
    build

APP_PATH="$BUILD_DIR/$APP_NAME"
[ -d "$APP_PATH" ] || APP_PATH="$(find "$BUILD_DIR" -maxdepth 1 -name '*.app' | head -n 1)"
[ -d "$APP_PATH" ] || die "xcodebuild produced no .app under $BUILD_DIR"
log "built $(basename "$APP_PATH") ($(du -sm "$APP_PATH" | cut -f1) MB)"

# -----------------------------------------------------------------------------
# 4) 收拾 .app：去掉签名残留与 macOS 垃圾文件
# -----------------------------------------------------------------------------
rm -rf "$APP_PATH/_CodeSignature"
find "$APP_PATH" -name '.DS_Store' -delete 2>/dev/null || true
find "$APP_PATH" -name '__MACOSX' -type d -prune -exec rm -rf {} + 2>/dev/null || true

# 二进制里的 arm64 校验（自签工具要求至少有一个 arm64 slice）
MAIN_BIN="$APP_PATH/$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$APP_PATH/Info.plist")"
if [ -f "$MAIN_BIN" ]; then
    log "arch: $(lipo -archs "$MAIN_BIN" 2>/dev/null || echo unknown)"
fi

# -----------------------------------------------------------------------------
# 5) 组 Payload 并打 zip —— ipa 就是「Payload/ 目录 + zip」
# -----------------------------------------------------------------------------
STAGE="$OUT/payload-stage"
rm -rf "$STAGE"
mkdir -p "$STAGE/Payload"
cp -R "$APP_PATH" "$STAGE/Payload/"

IPA_NAME="$(basename "$PROJECT").ipa"
IPA_PATH="$OUT/$IPA_NAME"
rm -f "$IPA_PATH"

( cd "$STAGE" && zip -qry "$IPA_PATH" Payload )
rm -rf "$STAGE"

# -----------------------------------------------------------------------------
# 6) 自检
# -----------------------------------------------------------------------------
log "ipa: $IPA_PATH ($(du -sm "$IPA_PATH" | cut -f1) MB)"

# 只做信息性检查：包内是否还有 .rpa（split 模式下不该有）
RPA_COUNT="$(unzip -l "$IPA_PATH" | grep -c '\.rpa$' || true)"
log "packed .rpa files: $RPA_COUNT"

if unzip -l "$IPA_PATH" | grep -q '^.*Payload/[^/]*\.app/base/game/'; then
    log "base/game/ present inside the app bundle"
else
    log "WARNING: no base/game/ inside the app bundle — did ios_create actually run?"
fi

( cd "$OUT" && shasum -a 256 "$IPA_NAME" > "$IPA_NAME.sha256" )

if [ "$KEEP_XCODE_BUILD" = "0" ]; then
    rm -rf "$BUILD_DIR"
fi

# GitHub Actions 里顺手把路径暴露出去
if [ -n "${GITHUB_OUTPUT:-}" ]; then
    {
        echo "ipa_path=$IPA_PATH"
        echo "ipa_name=$IPA_NAME"
        echo "ipa_size=$(stat -f%z "$IPA_PATH")"
        echo "bundle_id=$BUNDLE_ID"
    } >> "$GITHUB_OUTPUT"
fi

log "done"