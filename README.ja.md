# mcp-vroid

[English](README.md) | [日本語](README.ja.md)

**MCPクライアントからVRoid Studioを操作するツールです。** アプリの起動、画面の確認、部品の検索、クリック、文字入力、パラメーター変更、`.vroid` の保存、`.vrm` の書き出しをMCPツールとして提供します。

このリポジトリは、Nuri Hodges氏の **[nhodges/mcp-vroid](https://github.com/nhodges/mcp-vroid)** にWindows対応を追加したフォークです。元のLinux／Wayland実装、ドキュメント、著作権表記を維持しています。この日本語READMEでは、Windowsでの使い方と、元のLinux版の仕組み・使い方を説明します。

Windowsでは **pywinauto／Win32による入力・ウィンドウ管理** と **Pillowによる撮影** を追加し、既存のOCR、画像認識、VRoidの操作手順を利用します。元の18ツールの名前・引数・座標指定は維持しています。

- [Windowsでの導入](#windowsでの導入)
- [Linuxでの導入](#linuxでの導入)
- [ツール一覧](#ツール一覧)

## なぜGUIを操作するのか

VRoid Studioには、キャラクター編集を自動化するためのスクリプトAPIやCLI、プラグイン機構がありません。このツールは、人と同じように画面を見てマウスとキーボードで操作します。MCPクライアント側のモデルが画面を判断し、このサーバーが撮影や入力を担当します。

```text
画面撮影 → Tesseract／OpenCVで部品を検索 → 座標を取得 → マウス・キー入力
   ↑                                                        │
   └──────────────── 再撮影して結果を確認 ←──────────────────┘
```

## デモ

以下は**フォーク元のLinux版で、MCPクライアントから操作したデモ**です。

Bodyタブで数値を設定する例：
`vroid_open_tab("Body")` → `vroid_set_slider("Head Size", -0.15)`

![BodyタブのParametersパネルで数値を入力するデモ](docs/editor-parameters.png)

髪の編集画面でグループを選択し、Height、Interval、Twist Intensityなどを調整する例：

![髪の編集画面でパラメーターを変更するデモ](docs/hair-editor.png)

VRMの書き出し時に、VRM Settingsの必須項目を入力する例：

![VRM Settingsに名前と作者を入力するデモ](docs/export-vrm.png)

## Windowsでの導入

### 前提

- Windows 10／11
- Python **3.11以上**と **[uv](https://docs.astral.sh/uv/)**
- **Steam版VRoid Studio**（アプリID：`1486350`）
- VRoid Studioの **英語UI**。操作位置は **2.14.0** を基準にしています。
- **主モニター**で、VRoidを1つだけ起動し、1つの操作セッションで使用
- **Tesseract OCR** と英語の学習データ **`eng`**

日本語UIや一般的な複数モニターでの操作は、今回のWindows対応の対象外です。日本語の保存パスは利用できます。

### インストール

TesseractのWindows向け配布先は、[公式インストール案内](https://tesseract-ocr.github.io/tessdoc/Installation.html)を参照してください。インストール時に英語の学習データも用意します。

```powershell
git clone https://github.com/yub4-arema/mcp-vroid-forWindows
cd mcp-vroid-forWindows
uv sync --python 3.11
uv run python scripts/smoke_test.py
```

スモークテストはMCPサーバーを起動し、18ツールの一覧と `vroid_status` を確認します。VRoidが起動していなくても実行できます。

Windowsでは `native/build.sh` の実行や、`vpointer`、`grim`、`hyprctl`、X11の導入は不要です。Windows専用の直接依存は `pywinauto` と `pywin32`（`win32gui`、`win32api` などを直接使用）です。Pillow、OCR、OpenCV、VRoidの操作手順は既存のものを使用します。

### MCPクライアントへの登録

`mcpServers` 形式の設定例です。`C:\path\to\mcp-vroid-forWindows` を、実際にクローンしたフォルダーの絶対パスに置き換えてください。

```json
{
  "mcpServers": {
    "vroid": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\path\\to\\mcp-vroid-forWindows", "mcp-vroid"],
      "env": {
        "MCP_VROID_TESSERACT": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
      }
    }
  }
}
```

Tesseractの検出順序は、`MCP_VROID_TESSERACT`、`PATH`、標準のProgram Files配下の `Tesseract-OCR\tesseract.exe` です。MCPクライアントが環境変数を制限している場合は、上の例のように明示すると確実です。

登録後、クライアントから `vroid_status` を呼び、Tesseractのパスと `eng` データを確認してから `vroid_launch` を呼びます。

### Windowsでの動作

- 実行プロセスを確認した既存のVRoidウィンドウを再利用します。起動していなければSteam経由で起動し、最大化します。BOOTH版などSteam以外で導入した場合は、`MCP_VROID_EXE` に `VRoidStudio.exe` のフルパスを指定すると、そのexeを直接起動します。
- 操作前に、VRoid本体または同じプロセスに属する所有ダイアログが前面にあることを確認します。前面化に失敗した場合は入力せずエラーを返します。操作中はVRoidを前面に保ってください。
- Windowsの[前面ウィンドウに関する制限](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow)によって自動で前面にできない場合は、VRoidを手動で前面にして再実行します。
- `vroid_release` は、操作開始前に記憶したウィンドウがまだ存在する場合、そのウィンドウへ戻します。Windowsでは仮想デスクトップを操作せず、workspace関連の値は `null` になります。
- 撮影範囲はタイトルバーと枠を除いたクライアント領域です。撮影と入力には**物理ピクセル**を使用し、画像をクライアントへ送る際の縮小率は元の仕様を維持しています。
- `whole_screen=true` は、保存ダイアログも含めた仮想スクリーン全体（すべてのモニター）を撮影します。
- 保存・書き出しにはWindowsの絶対パスを渡します。Linux／Proton向けの `Z:\` 変換は行いません。空白や日本語を含むパスも使用できます。
- 名前を指定した保存とVRM書き出しは、**出力先が既に存在する場合、入力を始める前にエラー**になります。既存ファイルは削除しません。名前を指定しない通常の保存は、現在のプロジェクトを上書きします。
- ツール呼び出しはサーバー内で順番に実行し、マウスやキーの操作が重ならないようにしています。
- `vroid_launch(restart=true)` は、特定したVRoidプロセスだけを終了して再起動します。**未保存の変更は失われます。**

### 保存先と環境変数

| 環境変数 | Windowsでの既定値 | 用途 |
|---|---|---|
| `MCP_VROID_CAPTURES` | `%LOCALAPPDATA%\mcp-vroid\captures` | スクリーンショットの保存先 |
| `MCP_VROID_OUT` | `%LOCALAPPDATA%\mcp-vroid\out` | プロジェクト・VRMの既定の保存先 |
| `MCP_VROID_TESSERACT` | 自動検出 | Tesseract実行ファイルの指定 |
| `MCP_VROID_EXE` | 未設定（Steam経由で起動） | Steam以外で導入したVRoid Studioの実行ファイル |
| `MCP_VROID_MAX_IMAGE_PX` | `1600` | クライアントへ送る画像の最長辺。`0` は縮小しない |

保存先を環境変数で指定した場合は、その指定を優先します。

## Linuxでの導入

フォーク元は、**Arch Linux＋Hyprland、VRoid Studio 2.14.0の英語UI、Steam／Proton** で開発・検証されています。Linux版のウィンドウ管理はHyprlandに依存しています。

| 必要なもの | 用途 | 移植性 |
|---|---|---|
| **Hyprland 0.55以上** | `hyprctl` とLua dispatch APIによるウィンドウ検出、フォーカス、workspace管理 | Hyprland専用。主な処理は `driver/window.py` にあります |
| `grim` | 画面撮影 | `wlr-screencopy` を使えるwlroots系コンポジター |
| `zwlr_virtual_pointer_unstable_v1` | 実際のポインター移動とクリック | 対応するwlroots系コンポジター |
| **Xwayland**（`DISPLAY`） | X11 XTESTによるキー入力とスクロール | XwaylandのあるWayland環境 |
| Tesseract＋`eng` 学習データ | OCR | OS間で利用可能 |
| `gcc`、`wayland-scanner`、`libwayland-client` | ポインターヘルパーのビルド | ビルド環境が必要 |
| **Steam／Proton版VRoid Studio** | 操作対象のアプリ | Steam経由での起動を前提 |
| Python **3.11以上**、**uv** | MCPサーバー | OS間で利用可能 |

Arch Linuxでの依存導入例：

```bash
sudo pacman -S grim tesseract tesseract-data-eng wayland gcc pkgconf
```

以下はフォーク元のLinux／Hyprland向け導入手順です。

```bash
git clone https://github.com/nhodges/mcp-vroid
cd mcp-vroid
uv sync
bash native/build.sh    # Linuxでは必須
```

このフォークをLinuxで使用する場合は、クローン先を `https://github.com/yub4-arema/mcp-vroid-forWindows`、作業フォルダーを `mcp-vroid-forWindows` に置き換えます。

`native/build.sh` は、Waylandのvirtual-pointerプロトコルを使う小さなCヘルパーをビルドします。ビルドしないとポインター操作は `native/vpointer missing` で失敗します。`vroid_status` でヘルパーの有無を確認できます。

Claude Codeへの登録例：

```bash
claude mcp add vroid -- uv run --directory /path/to/mcp-vroid mcp-vroid
```

`mcpServers` 形式での登録例：

```json
{
  "mcpServers": {
    "vroid": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-vroid", "mcp-vroid"]
    }
  }
}
```

MCPクライアントがデスクトップ用の環境変数を渡さない場合、Linux版は起動時に `XDG_RUNTIME_DIR`、`WAYLAND_DISPLAY`、`HYPRLAND_INSTANCE_SIGNATURE`、`DISPLAY` を補います。既に設定されている値を優先し、補った値は `vroid_status` に表示します。

Linuxの既定の保存先は `$XDG_STATE_HOME/mcp-vroid/captures` と `$XDG_STATE_HOME/mcp-vroid/out` です。`XDG_STATE_HOME` が未設定なら `~/.local/state` を使います。`MCP_VROID_CAPTURES`、`MCP_VROID_OUT`、`MCP_VROID_MAX_IMAGE_PX` はWindowsと共通で、Linuxのポインターヘルパーは `MCP_VROID_VPOINTER` で指定できます。

## ツール一覧

既存の**18ツール**を提供します。表では主な引数を示しています。

### 起動・状態・復帰

| ツール | 内容 |
|---|---|
| `vroid_launch(restart=false, timeout=240)` | 必要ならSteamからVRoidを起動し、操作できる状態にします。Windowsは最大化、LinuxはHyprlandのworkspace 9へ移動してフルスクリーン化します |
| `vroid_status()` | ウィンドウ、フォーカス、座標、保存先、使用バックエンド、必要な外部ツールを確認します。WindowsではTesseractの検出パスと `eng` データも表示します |
| `vroid_release()` | Windowsは元の前面ウィンドウ、Linuxは元のworkspaceへ戻ります。VRoidは起動したままです |

### 画面の確認・検索

| ツール | 内容 |
|---|---|
| `vroid_screenshot(region?, tag?, whole_screen?, full_resolution?)` | ウィンドウまたは画面全体を撮影して保存し、MCP画像として返します。元の画像サイズと転送時の縮小率を報告します |
| `vroid_find_text(query, region?, exact?, limit?)` | 新しく撮影した画像をOCRにかけ、文字の位置と中心座標を返します。`region` で範囲を絞ると高速です |
| `vroid_find_button(color='primary'\|'disabled', label?, region?)` | OCRが読み落としやすい青いボタンを色で検索します。灰色は無効なボタンです |
| `vroid_current_screen()` | `start`、`editor`、`export_vrm`、`hair_editor`、`unknown` のいずれかを返します |

### マウス・キーボード操作

| ツール | 内容 |
|---|---|
| `vroid_click(x, y, space='image', button='left', double=false)` | ポインターを移動してクリックします。ダブルクリックにも対応します |
| `vroid_drag(x1, y1, x2, y2, space='image', button='left')` | ボタンを押して段階的に移動し、離します。右ドラッグはカメラの回転、中ドラッグは平行移動に使います |
| `vroid_scroll(dy, dx=0, x?, y?, space='image')` | 縦・横スクロールします。正の `dy` は下方向です。対象パネル上にポインターを置いて使います |
| `vroid_type(text, clear_first=false)` | フォーカスのある入力欄へ文字列を入力します。Windowsでは特殊記号も文字として入力し、改行はEnterにします |
| `vroid_key(combo, times=1)` | `Return`、`Escape`、`ctrl+s`、`ctrl+shift+s` などのキー操作を送ります |

### VRoidの操作手順

| ツール | 内容 |
|---|---|
| `vroid_new_character(base='Fem'\|'Masc')` | スタート画面から新規作成し、ベースを選んで編集画面へ進みます |
| `vroid_open_tab(name)` | Face、Hairstyle、Body、Outfit、Accessories、Lookのタブへ切り替えます |
| `vroid_set_slider(label, value)` | Parametersパネルの行を探し、数値欄に値を入力します |
| `vroid_set_color(label, hex)` | 色の行を探し、`#RRGGBB` の値を入力します |
| `vroid_export_vrm(path, avatar_name, creator, version='1.0')` | 書き出し画面、VRM Settings、保存ダイアログを順に操作します。`version` は `1.0` または `0.0` です |
| `vroid_save_project(name?)` | 名前を指定すると明示した `.vroid` パスへ保存し、省略すると通常の保存を行います |

## 操作の流れと座標

基本は**撮影 → 検索 → 操作 → 再撮影**です。

1. `vroid_launch()` で起動・前面化します。
2. `vroid_screenshot()` の画像を確認します。
3. `vroid_find_text` や `vroid_find_button` で対象の座標を得ます。
4. **直近の撮影から得た座標**でクリックなどを行います。
5. 再撮影して結果を確認します。

ツールの既定の座標は `space="image"`、つまりVRoidウィンドウの撮影画像のピクセルです。`vroid_find_text` の結果は、そのまま `vroid_click` に渡せます。

| `space` | Windows | Linux／Hyprland |
|---|---|---|
| `image` | 撮影画像のピクセル | 撮影画像のピクセル |
| `window` | クライアント領域の左上を基準とした物理ピクセル | ウィンドウの左上を基準とした論理座標 |
| `layout` | デスクトップ全体の絶対位置を示す物理ピクセル | デスクトップ全体の絶対位置を示す論理座標 |

クライアントへ届く画像が縮小されている場合、画像上で読んだ座標は、報告された `downscale` の逆数を掛けて元の座標に戻します。`vroid_find_text` などが返す座標は、既に元の画像のピクセルです。

Linuxの基準環境では、Hyprlandの論理座標が2048×1152、撮影画像とXwaylandが2560×1440でした。Linuxはこの差を内部で変換します。WindowsはGUIライブラリを読み込む前にDPI設定を行い、撮影と入力を物理ピクセルに統一します。

## 仕組みと制約

Linuxの撮影は `grim`、ポインター操作は `native/vpointer.c` によるWaylandのvirtual-pointer、キーとスクロールはXwaylandのXTESTを使います。WindowsはPillow、pywinauto、Win32を使います。文字検索はTesseract、ボタンの色や画像の検索はOpenCVで行います。

GUI操作には次の制約があります。

- **UIのバージョンと言語に依存します。** 英語UIのVRoid Studio 2.14.0を基準としているため、画面構成の変更や別言語では調整が必要になることがあります。
- **OCRには読み落としや誤読があります。** 小さい文字や青いボタン上の白文字は特に不安定です。ボタンは `vroid_find_button` で色を検索し、数値はドラッグより入力欄を優先します。
- **モーダルダイアログが操作を遮ることがあります。** 検索範囲だけでなく、必要に応じて画面全体を確認してください。
- **読み込みや書き出しには時間がかかります。** 重いモデルでは待ち時間が長くなります。
- **3D表示の差分だけでは操作結果を判定しにくいことがあります。** パラメーター欄やタブなど、UI部分を確認します。
- **保存ダイアログは別ウィンドウです。** 状態確認には `vroid_screenshot(whole_screen=true)` を使います。
- **1インスタンス・1セッションで使用します。** 実際のデスクトップを操作するため、ヘッドレス実行や複数セッションの並行操作は対象外です。

タブ、パネル、髪の編集画面、書き出し手順の詳しい説明は、フォーク元の **[UIマップ（英語）](docs/ui-map.md)** にあります。記載座標は元のLinux基準環境で測定したものです。

## デスクトップ操作について

このサーバーは、使用中のデスクトップに実際のマウス・キーボード入力を送り、スクリーンショットをファイルに保存します。

- `whole_screen=true` には、VRoid以外の画面情報が写る場合があります。画像は暗号化せず保存されます。
- フォーカス確認は行いますが、VRoid内でどこを操作するかはクライアントの指示に依存します。
- `restart=true` は未保存の変更を失わせます。
- 各操作に個別の確認ダイアログを出す仕組みはありません。

フォーク元と同様、**画面を確認できる状態での使用を推奨します。** 共有デスクトップでの実行を避け、撮影画像の扱いに注意してください。操作終了時は `vroid_release()` でデスクトップを戻します。

## 開発

```powershell
uv run python -m unittest discover -s tests -v
uv run python scripts/smoke_test.py
uv run python scripts/smoke_test.py --screenshot
uv run vroid-driver shot
```

単体テストは実際のマウス・キー入力を送りません。`--screenshot` 付きのスモークテストは、VRoidが起動中なら撮影を追加します。

Windowsの実機テスト用に `scripts/windows_acceptance.py` を用意しています。新規テストモデルを使い、次のフェーズを順に実行します。

```powershell
uv run python scripts/windows_acceptance.py create
uv run python scripts/windows_acceptance.py edit
uv run python scripts/windows_acceptance.py color
uv run python scripts/windows_acceptance.py save
uv run python scripts/windows_acceptance.py export10
uv run python scripts/windows_acceptance.py export00
uv run python scripts/windows_acceptance.py reopen
uv run python scripts/windows_acceptance.py alignment
```

撮影と実行結果はチェックアウト内に、モデルは `out/windows-acceptance/日本語 models` に保存します。繰り返す場合は、各フェーズに同じ `--out` を指定し、新しい出力フォルダーを使ってください。既存の保存・書き出し先は上書きしません。

自動で前面にできない場合は `--wait-foreground` を付け、手動でVRoidを前面にします。DPI別の座標確認は、Windowsの表示倍率を手動で変更してから `alignment --wait-foreground --dpi 96`（100％）、`--dpi 120`（125％）、`--dpi 144`（150％）で実行できます。スクリプト自体は表示設定を変更しません。

`vroid-driver` はMCPと同じ操作エンジンを使うCLIです。`launch`、`shot`、`find`、`click`、`tab`、`slider`、`export`、`cam`、`apply-params` などをデバッグに利用できます。

主なファイル構成：

```text
src/mcp_vroid/server.py       MCPツール定義（stdio）
src/mcp_vroid/session_env.py  WindowsのDPI設定／Linuxの環境変数復元
src/mcp_vroid/driver/
  window.py                  ウィンドウ管理とOS分岐
  windows.py                 Windows専用の撮影・入力・ウィンドウ処理
  capture.py                 撮影と座標変換
  locate.py                  OCR、色・画像による部品検索
  input.py                   マウスとキーボード入力
  actions.py                 VRoidの操作手順
native/vpointer.c            Linux用のWaylandポインターヘルパー
```


## フォーク元とライセンス

元のプロジェクトは **[nhodges/mcp-vroid](https://github.com/nhodges/mcp-vroid)**、作者は **Nuri Hodges氏**です。Windows対応は、このフォークで追加しています。

**MIT License**。元の著作権表記とライセンスを維持しています。詳しくは [LICENSE](LICENSE) を参照してください。

VRoid Studioはpixiv Inc.の製品です。このプロジェクトはpixivとは関係がなく、アプリのUIを操作する非公式ツールです。
