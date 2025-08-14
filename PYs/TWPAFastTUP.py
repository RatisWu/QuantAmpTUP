# experiment.py
import sys, os
from LiteInstru.Worker.TWPA_FastTuneUP import TWPA_fastTup


def main():
    # 取得上傳的 TOML 檔路徑
    if len(sys.argv) < 2:
        print("請提供 TOML 檔案路徑")
        sys.exit(1)
    
    toml_path = sys.argv[1]
    print(f"收到 TOML 檔案: {toml_path}")

    path = TWPA_fastTup(toml_path)


if __name__ == "__main__":
    main()