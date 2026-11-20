#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_project.py —— 把 ios_create 生成的 Xcode 工程改成「可直接无签名编译 + 文件 App 能看见 Documents」。

ios_create（renios/buildlib/renios/create.py）生成的工程能编译，但有几处不适合
自签分发，这里统一收拾：

  1. Info.plist
     * CFBundleDisplayName 从 $(PRODUCT_NAME) 改成真正的显示名（桌面图标下的名字）。
     * CFBundleIdentifier 从 $(PRODUCT_BUNDLE_IDENTIFIER) 改成显式字符串 —— 自签工具
       （SideStore / AltStore / LiveContainer）要按 bundle id 管理重装，让它可预测。
     * 补 UIFileSharingEnabled / LSSupportsOpeningDocumentsInPlace —— 这是「文件」App
       里能看到 <App>/Documents 并往里拖素材的唯一开关，也就是外置素材方案的前提。
     * CFBundleShortVersionString / CFBundleVersion 用我们自己的版本号。

  2. project.pbxproj
     * DEVELOPMENT_TEAM = TEAMID → 空。
     * CODE_SIGN_IDENTITY[sdk=iphoneos*] = "iPhone Developer" → 空。
       （真正生效的是 xcodebuild 命令行里的 CODE_SIGNING_ALLOWED=NO，这里只是别让
       别人误以为要证书。）
     * PRODUCT_NAME / PRODUCT_BUNDLE_IDENTIFIER 统一。

  3. 顺手把 target 名、product 名、bundle id 写进 <project>/ios-build.json，
     给 build_ios_ipa.sh 用 —— 不要靠 shell 里 grep pbxproj。

用法：
  python3 fix_project.py --project /path/to/_out/MyGame \\
      --display-name "My Game" --bundle-id com.julyfinal.milkyTouch --version 1.0.0
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import sys


def log(msg: str) -> None:
    print("[fix_project] " + msg, flush=True)


def find_xcodeproj(project_dir: str) -> str:
    for name in sorted(os.listdir(project_dir)):
        if name.endswith(".xcodeproj"):
            return os.path.join(project_dir, name)
    raise SystemExit("fix_project: no *.xcodeproj under %s" % project_dir)


def patch_plist(project_dir: str, display_name: str, bundle_id: str,
                version: str, build_number: str) -> str:
    path = os.path.join(project_dir, "Info.plist")
    with open(path, "rb") as f:
        pl = plistlib.load(f)

    pl["CFBundleDisplayName"] = display_name
    pl["CFBundleName"] = display_name
    pl["CFBundleIdentifier"] = bundle_id
    pl["CFBundleShortVersionString"] = version
    pl["CFBundleVersion"] = build_number

    # 「文件」App 可见性 —— 外置素材方案的前提
    pl["UIFileSharingEnabled"] = True
    pl["LSSupportsOpeningDocumentsInPlace"] = True

    # 自签安装经常被系统当成「不支持全屏的设备」处理，显式要求全屏更保险。
    pl["UIRequiresFullScreen"] = True
    pl["UIStatusBarHidden"] = True
    pl.pop("UIStatusBarStyle", None)

    # 引擎只用横屏（renios 的 prototype 就是横屏），别继承竖屏免得黑屏。
    pl["UISupportedInterfaceOrientations"] = [
        "UIInterfaceOrientationLandscapeRight",
        "UIInterfaceOrientationLandscapeLeft",
    ]

    with open(path, "wb") as f:
        plistlib.dump(pl, f, sort_keys=True)

    log("Info.plist: display=%r bundle=%s version=%s(%s) filesharing=on"
        % (display_name, bundle_id, version, build_number))
    return path


def target_name_from_pbxproj(pbx: str) -> str:
    """从 PBXNativeTarget 段里取 name = XXX;"""
    m = re.search(r"isa = PBXNativeTarget;[^}]*?name = (\"[^\"]*\"|[A-Za-z0-9_.-]+);",
                  pbx, re.S)
    if m:
        return m.group(1).strip('"')
    # 兜底：project.xcodeproj 的 basename
    return ""


def patch_pbxproj(xcodeproj: str, bundle_id: str, product_name: str) -> tuple:
    pbx_path = os.path.join(xcodeproj, "project.pbxproj")
    with open(pbx_path, "r", encoding="utf-8", errors="replace") as f:
        pbx = f.read()

    target = target_name_from_pbxproj(pbx) or product_name

    # 无签名：把模板里留下的占位符清掉
    pbx = re.sub(r"DEVELOPMENT_TEAM = [^;]*;", 'DEVELOPMENT_TEAM = "";', pbx)
    pbx = re.sub(r'("?CODE_SIGN_IDENTITY\[sdk=iphoneos\*\]"?\s*=\s*)"[^"]*";',
                 r'\1"";', pbx)

    # build 设置里的 PRODUCT_NAME / bundle id 统一（两份 configuration 各一遍）
    pbx = re.sub(r"PRODUCT_NAME = [^;]*;", "PRODUCT_NAME = %s;" % product_name, pbx)
    pbx = re.sub(r"PRODUCT_BUNDLE_IDENTIFIER = [^;]*;",
                 "PRODUCT_BUNDLE_IDENTIFIER = %s;" % bundle_id, pbx)

    with open(pbx_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(pbx)

    log("pbxproj: target=%r product=%r bundle=%s" % (target, product_name, bundle_id))
    return target, product_name


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fix up an ios_create-generated Xcode project")
    ap.add_argument("--project", required=True, help="directory produced by ios_create")
    ap.add_argument("--display-name", default=None, help="name shown under the icon")
    ap.add_argument("--bundle-id", default=None)
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--build-number", default="1")
    args = ap.parse_args(argv)

    project_dir = os.path.abspath(args.project)
    if not os.path.isdir(project_dir):
        log("ERROR: %s not found" % project_dir)
        return 2

    xcodeproj = find_xcodeproj(project_dir)
    base = os.path.basename(xcodeproj)[: -len(".xcodeproj")]

    display_name = args.display_name or base
    bundle_id = args.bundle_id or ("com.domain." + base)
    product_name = re.sub(r"[^A-Za-z0-9_.-]", "", base) or "app"

    patch_plist(project_dir, display_name, bundle_id, args.version, args.build_number)
    target, product = patch_pbxproj(xcodeproj, bundle_id, product_name)

    info = dict(
        xcodeproj=os.path.basename(xcodeproj),
        target=target,
        product_name=product,
        app_name=product + ".app",
        display_name=display_name,
        bundle_id=bundle_id,
        version=args.version,
        build_number=args.build_number,
    )
    out = os.path.join(project_dir, "ios-build.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2, sort_keys=True)
    log("wrote %s" % out)

    return 0


if __name__ == "__main__":
    sys.exit(main())