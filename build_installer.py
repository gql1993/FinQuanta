"""
打包客户端为独立可执行文件。
运行: python build_installer.py
输出: dist/AI量化交易平台/ 目录
"""
import subprocess
import sys
import os

def main():
    print("=" * 60)
    print("AI 量化交易平台 - 打包构建")
    print("=" * 60)

    # 确保资源文件存在
    required = [
        "desktop/resources/plotly.min.js",
        "data_cache/board_builtin.json",
        "data_cache/strategy_catalog.json",
        "data_cache/quant.db",
    ]
    for f in required:
        if not os.path.exists(f):
            print(f"[WARNING] 缺少文件: {f}")

    print("\n开始打包...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "build_desktop.spec",
        "--noconfirm",
        "--clean",
    ]
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))

    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("打包成功！")
        print(f"输出目录: {os.path.abspath('dist/AI量化交易平台')}")
        print("将整个文件夹发给其他人即可使用。")
        print("运行方式: 双击 AI量化交易平台.exe")
        print("=" * 60)
    else:
        print(f"\n打包失败，返回码: {result.returncode}")

if __name__ == "__main__":
    main()
