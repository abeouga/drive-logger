"""アプリの名前に使う字体（Dela Gothic One）から、名前の字だけを取り出した小さな woff2 を作る。

元の日本語の字体は 1 ファイル約 940 KB あり、名前の 7 字のために全部を配るのは重い。
名前の字だけに絞ると数 KB になる。字体は SIL Open Font License 1.1（Reserved Font Name なし）で、
絞った版を配ってよい。ライセンスの文は src/assets/fonts/ に一緒に置く。

アプリの名前（src/components/AppShell.tsx の APP_NAME）を変えたら、これを流し直す。

  python -m pip install fonttools brotli
  python scripts/subset-brand-font.py

元の字体は devDependencies の @fontsource/dela-gothic-one から読む（npm ci のあとに流す）。
"""

import re
import sys
from pathlib import Path

from fontTools import subset

WEB = Path(__file__).resolve().parent.parent
SOURCE = WEB / "node_modules/@fontsource/dela-gothic-one/files/dela-gothic-one-japanese-400-normal.woff2"
SHELL = WEB / "src/components/AppShell.tsx"
OUT = WEB / "src/assets/fonts/dela-gothic-one-brand.woff2"


def app_name() -> str:
    match = re.search(r'export const APP_NAME = "([^"]+)"', SHELL.read_text(encoding="utf-8"))
    if not match:
        sys.exit(f"APP_NAME が見つかりません：{SHELL}")
    return match.group(1)


def main() -> None:
    if not SOURCE.exists():
        sys.exit(f"元の字体がありません（npm ci を先に流す）：{SOURCE}")
    text = app_name()
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["*"]
    options.name_IDs = ["*"]  # 著作権とライセンスの記載を残す
    options.notdef_outline = True
    font = subset.load_font(str(SOURCE), options)
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subset.save_font(font, str(OUT), options)
    print(f"{OUT.relative_to(WEB)}：{text}（{OUT.stat().st_size:,} バイト）")


if __name__ == "__main__":
    main()
