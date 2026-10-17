# check_printer

**English** · [中文](#中文)

Prints checks on blank letter-size **check-on-top voucher stock**: the check is the top 3.5", with
perforations at 3.5" and 7" and two stubs below. You get a PDF to print, and each check is logged in a register.

There are two ways to use it, and both share the same `config.json` and `checks/` folder:

- **Windows app** (`app.py`, or the packaged `CheckPrinter.exe`): fill in a form, click a button.
- **Command line** (`make_check.py`): one command per check, handy for scripts.

## Requirements

- Python 3.10 or newer (tested on 3.12 and 3.13), with tkinter for the app
- A laser printer and blank check-on-top voucher stock
- To build the exe: Windows Python from [python.org](https://www.python.org/downloads/windows/)

## Install

With conda (recommended, keeps the packages separate from your other projects):

```bash
conda create -n checkprinter -c conda-forge python=3.12 -y
conda activate checkprinter
python -m pip install -r requirements.txt
```

Or with any Python 3.10+: `python -m pip install -r requirements.txt`.

## Configure

Run the app and fill in the **Settings** tab (it opens automatically the first time), or copy
`config.example.json` to `config.json` and edit it by hand. Copy the routing and account numbers
**exactly as printed at the bottom of your existing checks**.

| field | meaning |
|---|---|
| `payer` | your name/business and address lines, printed top-left |
| `bank` | bank name, address lines, and optional fractional routing number (e.g. `12-3456/7890`) |
| `routing_number` | 9 digits; checked against the ABA checksum. It can differ from your ACH/wire number |
| `account_number` | digits and dashes only |
| `micr_style` | `business`: `⑈001234⑈ ⑆routing⑆ account⑈` · `personal`: `⑆routing⑆ account⑈ 1234` |
| `micr_check_number_digits` | check number is zero-padded to this many digits in the MICR line (business style) |
| `first_check_number` | used until the register has checks in it; after that numbering continues from the highest |
| `date_format` | Python `strftime` format, default `%m/%d/%Y` |
| `signature_image` | optional transparent PNG, printed above the signature line; `null` to sign by hand |
| `offset_x`, `offset_y` | printer calibration in inches (+x right, +y down), see [Calibration](#calibration) |

## Using the app

```bash
conda activate checkprinter
python app.py
```

**Write a check** tab:

1. Check No. and Date are filled in for you. Change them if needed.
2. Enter the payee, the amount (the amount in words appears below as you type) and an optional memo.
3. Click **Sample (VOID)** to preview a watermarked copy. It isn't logged and doesn't use up a number.
4. Click **Create check**. The PDF opens; print it at **Actual size / 100%**.
   It's saved as `checks/check_001001.pdf` and logged in `checks/register.csv`.

**Open checks folder** shows all the PDFs. Open `register.csv` in Excel to see every check you've written.
To reprint a check, open its PDF again.

**Settings** tab: payer, bank, MICR details, signature and calibration. **Save** checks everything
before it writes `config.json`. **Save + alignment page** also prints the calibration sheet.

## Command line

```bash
python make_check.py --payee "Acme Plumbing LLC" --amount 1234.56 --memo "Invoice 4471"
python make_check.py            # asks for payee, amount and memo
```

| option | meaning |
|---|---|
| `--payee`, `--amount`, `--memo` | the check (amount like `1234.56`; `,` and `$` are allowed) |
| `--date YYYY-MM-DD` | default: today |
| `--number N` | default: next number from the register |
| `--reprint` | allow a number already in the register (saved as `check_001001-2.pdf`; the original stays as it was) |
| `--address LINE` | payee address line for a double-window envelope (repeat up to 3 times) |
| `--item "Desc=123.45"` | line item printed on both stubs (repeatable) |
| `--sample` | VOID watermark, not logged |
| `--align` | sample plus alignment guides, for calibration |
| `-o PATH`, `--config PATH` | output PDF path / config file |

`--address` and `--item` are only available on the command line.

## Building the Windows exe

PyInstaller can't cross-compile, so the exe has to be built with **Windows** Python. Install it from
python.org first and tick **Add python.exe to PATH** (its default install includes tkinter).

**Option A: from WSL, one command**

```bash
./build_from_wsl.sh
```

It copies the source to `%USERPROFILE%\CheckPrinterBuild` (your `config.json` is never copied), runs
`build_exe.bat` there, and opens the result in Explorer:
`%USERPROFILE%\CheckPrinterBuild\dist\CheckPrinter\CheckPrinter.exe`.

**Option B: on Windows**

Copy the project folder to Windows and double-click `build_exe.bat`. The result is
`dist\CheckPrinter\CheckPrinter.exe` inside that folder.

What `build_exe.bat` does:

1. Finds Windows Python (`py` or `python`) and checks it has tkinter.
2. Creates `.venv-win\` (first build only) and installs PyInstaller plus `requirements.txt` into it.
3. Builds a folder app (`--onedir`): it starts faster than a single-file exe and antivirus flags it less often.
4. Copies `fonts\` and `config.example.json` next to the exe. The GnuMICR license asks for the font to ship
   alongside the program rather than inside it.
5. Updates `dist\CheckPrinter` while keeping any `config.json` and `checks\` already there.

**Running and sharing the exe**

- Copy the **whole** `CheckPrinter` folder anywhere (not just the exe) and run `CheckPrinter.exe`.
  No Python is needed on that PC.
- `config.json` and `checks\` are created next to the exe. If that folder isn't writable (e.g. Program Files),
  they go to `%APPDATA%\CheckPrinter` instead.
- The exe isn't code-signed. On a PC where it arrived by download or email, Windows SmartScreen may warn;
  click **More info → Run anyway**.
- To update, rebuild and run the build again. Your settings and checks are kept.
  Don't send someone a folder that has your `config.json` or `checks\` in it.

## Calibration

Every printer feeds paper slightly differently, and the MICR line must sit within a narrow band for
the bank's readers. Do this once per printer and paper tray:

1. Click **Save + alignment page** (or run `python make_check.py --align --payee Test --amount 1`).
2. Print `checks/sample.pdf` on **plain paper** at **Actual size / 100%**, never "Fit to page".
3. Hold it behind a blank check against a window. The dashed lines should match the perforations.
4. If they don't, adjust Offset X / Y (inches) in Settings and repeat.
5. Print one sample on real check stock before writing a live check.

## Printing and bank acceptance

- The MICR line uses the E-13B font in `fonts/` (GnuMICR, GPL; see `fonts/README`), placed 3/16" above
  the check's bottom edge at 8 characters per inch, as ANSI X9.13 specifies.
- Use a laser printer. **MICR (magnetic) toner** is the safe choice for checks you mail to other people.
  Most banks clear from images now, so regular toner usually works. Don't use inkjet: it smears and washes off.
- Take a sample check to your bank and have them verify the MICR line before you rely on it.

## Privacy

`config.json` (account number), `checks/` (every PDF has your account number in its MICR line) and a
signature image are private. `.gitignore` already excludes them, along with all `*.pdf` files.
Name your signature file `signature.png` or `signature_*.png` so it's ignored too.
Anyone who can run the app with a signature image set can print signed checks.

## Files

| file | purpose |
|---|---|
| `app.py` | Windows app (tkinter) |
| `make_check.py` | check layout, MICR, register, and the command line |
| `config.example.json` | template for `config.json` |
| `requirements.txt` | Python packages (reportlab, Pillow) |
| `build_exe.bat`, `build_from_wsl.sh` | build `CheckPrinter.exe` |
| `fonts/` | GnuMICR E-13B font and its license |
| `icon.ico` | app icon |

## Troubleshooting

| problem | fix |
|---|---|
| `routing_number ... fails the ABA checksum` | a digit is wrong; copy it again from an existing check |
| "Can't write the PDF" | that PDF is open in a viewer; close it and try again |
| printed too small or shifted | print at Actual size / 100%, then calibrate |
| `build_exe.bat`: Windows Python with tkinter was not found | install Python from python.org with "Add python.exe to PATH" ticked |
| "MICR font not found" | copy the whole `CheckPrinter` folder, including `fonts\` |

---

<a id="中文"></a>

# check_printer（中文）

[English](#check_printer) · **中文**

在空白 Letter 尺寸的 **支票在上式凭单支票纸**上打印支票：上方 3.5 英寸是支票，3.5 英寸和 7 英寸处有齿孔，
下面是两联存根。程序生成 PDF 供打印，每张支票都会记入登记簿。

有两种用法，共用同一个 `config.json` 和 `checks/` 文件夹：

- **Windows 程序**（`app.py`，或打包后的 `CheckPrinter.exe`）：填表、点按钮。
- **命令行**（`make_check.py`）：一条命令开一张，适合写脚本。

> 程序界面为英文，下文中的按钮和标签名保留英文原文。

## 环境要求

- Python 3.10 及以上（已在 3.12、3.13 上测试），图形界面需要 tkinter
- 激光打印机和空白“支票在上式”凭单支票纸
- 打包 exe 需要：[python.org](https://www.python.org/downloads/windows/) 提供的 Windows 版 Python

## 安装

推荐用 conda，依赖与其他项目隔离：

```bash
conda create -n checkprinter -c conda-forge python=3.12 -y
conda activate checkprinter
python -m pip install -r requirements.txt
```

也可以用任意 Python 3.10+：`python -m pip install -r requirements.txt`。

## 配置

运行程序，在 **Settings** 页填写（首次运行会自动打开该页）；或者把 `config.example.json`
复制为 `config.json` 手动编辑。路由号和账号要**照抄现有支票底部印的号码**。

| 字段 | 含义 |
|---|---|
| `payer` | 你的姓名/公司名和地址，印在左上角 |
| `bank` | 银行名称、地址，以及可选的分数式路由号（如 `12-3456/7890`） |
| `routing_number` | 9 位，会做 ABA 校验位检查。可能与 ACH/电汇路由号不同 |
| `account_number` | 只能包含数字和短横线 |
| `micr_style` | `business`（商业）：`⑈001234⑈ ⑆routing⑆ account⑈` · `personal`（个人）：`⑆routing⑆ account⑈ 1234` |
| `micr_check_number_digits` | MICR 行中支票编号补零后的位数（business 格式） |
| `first_check_number` | 登记簿为空时使用的编号；之后从已有最大编号往后续 |
| `date_format` | Python `strftime` 格式，默认 `%m/%d/%Y` |
| `signature_image` | 可选，透明背景 PNG 签名，印在签名线上方；设为 `null` 则手签 |
| `offset_x`, `offset_y` | 打印校准偏移，单位英寸（+x 向右，+y 向下），见[打印校准](#打印校准) |

## 使用图形界面

```bash
conda activate checkprinter
python app.py
```

**Write a check**（开支票）页：

1. 编号（Check No.）和日期（Date）已自动填好，需要时可修改。
2. 填写收款人、金额（输入时下方会实时显示英文大写）和可选的备注。
3. 点 **Sample (VOID)** 预览带水印的样张：不登记，不占用编号。
4. 点 **Create check** 生成支票。PDF 自动打开，按 **实际大小 / 100%** 打印。
   文件保存为 `checks/check_001001.pdf`，并记入 `checks/register.csv`。

**Open checks folder** 打开所有 PDF 所在的文件夹。用 Excel 打开 `register.csv` 可查看全部开票记录。
要重新打印某张支票，再次打开它的 PDF 即可。

**Settings**（设置）页：付款人、银行、MICR 信息、签名和校准。**Save** 会先校验所有内容再写入 `config.json`；
**Save + alignment page** 保存后还会生成校准页。

## 命令行

```bash
python make_check.py --payee "Acme Plumbing LLC" --amount 1234.56 --memo "Invoice 4471"
python make_check.py            # 按提示输入收款人、金额和备注
```

| 参数 | 含义 |
|---|---|
| `--payee`、`--amount`、`--memo` | 收款人、金额（如 `1234.56`，可带 `,` 和 `$`）、备注 |
| `--date YYYY-MM-DD` | 默认今天 |
| `--number N` | 默认取登记簿中的下一个编号 |
| `--reprint` | 允许使用登记簿中已有的编号（另存为 `check_001001-2.pdf`，原文件不变） |
| `--address LINE` | 收款人地址行，用于双窗信封（最多重复 3 次） |
| `--item "描述=123.45"` | 存根明细，两联存根都会打印（可重复） |
| `--sample` | VOID 水印，不登记 |
| `--align` | 样张加对齐参考线，用于校准 |
| `-o PATH`、`--config PATH` | 输出 PDF 路径 / 配置文件路径 |

`--address` 和 `--item` 只有命令行支持。

## 打包 Windows exe

PyInstaller 不能跨平台编译，exe 必须用 **Windows 版** Python 打包。请先从 python.org 安装，
安装时勾选 **Add python.exe to PATH**（默认安装已包含 tkinter）。

**方式 A：在 WSL 中一条命令完成**

```bash
./build_from_wsl.sh
```

脚本会把源码复制到 `%USERPROFILE%\CheckPrinterBuild`（不会复制你的 `config.json`），在那里运行
`build_exe.bat`，完成后用资源管理器打开结果：
`%USERPROFILE%\CheckPrinterBuild\dist\CheckPrinter\CheckPrinter.exe`。

**方式 B：在 Windows 上**

把项目文件夹复制到 Windows，双击 `build_exe.bat`。结果在该文件夹下的 `dist\CheckPrinter\CheckPrinter.exe`。

`build_exe.bat` 做了这些事：

1. 查找 Windows 版 Python（`py` 或 `python`），并确认有 tkinter。
2. 创建 `.venv-win\`（仅首次），在其中安装 PyInstaller 和 `requirements.txt` 中的依赖。
3. 以文件夹形式打包（`--onedir`）：比单文件 exe 启动更快，也更少被杀毒软件误报。
4. 把 `fonts\` 和 `config.example.json` 复制到 exe 旁边。GnuMICR 许可证要求字体随程序一起分发，而不是打包进 exe。
5. 更新 `dist\CheckPrinter`，保留其中已有的 `config.json` 和 `checks\`。

**运行和分发 exe**

- 复制**整个** `CheckPrinter` 文件夹（不能只复制 exe）到任意位置，运行 `CheckPrinter.exe`。
  目标电脑不需要安装 Python。
- `config.json` 和 `checks\` 会创建在 exe 旁边。如果该目录不可写（如 Program Files），
  则改存到 `%APPDATA%\CheckPrinter`。
- exe 没有代码签名。通过下载或邮件拿到 exe 的电脑上，Windows SmartScreen 可能会弹出警告，
  点 **更多信息 → 仍要运行** 即可。
- 更新程序：重新运行打包即可，设置和支票记录都会保留。
  分发给别人时，不要把含有你的 `config.json` 或 `checks\` 的文件夹发出去。

<a id="打印校准"></a>

## 打印校准

每台打印机的进纸位置都略有不同，而 MICR 行必须落在很窄的区域内，银行设备才能识别。
每台打印机、每个纸盒校准一次即可：

1. 点 **Save + alignment page**（或运行 `python make_check.py --align --payee Test --amount 1`）。
2. 用**普通纸**按**实际大小 / 100%** 打印 `checks/sample.pdf`，切勿选择“适合页面”。
3. 把打印页叠在空白支票纸后面，对着窗户透光查看，虚线应与齿孔重合。
4. 如有偏差，在 Settings 中调整 Offset X / Y（英寸），然后重复。
5. 正式开票前，先在真实支票纸上打印一张样张确认。

## 打印与银行接受

- MICR 行使用 `fonts/` 中的 E-13B 字体（GnuMICR，GPL 许可，见 `fonts/README`），
  按 ANSI X9.13 规范位于距支票底边 3/16 英寸处，每英寸 8 个字符。
- 请用激光打印机。寄给他人的支票最好使用 **MICR（磁性）墨粉**。
  如今大多数银行通过图像清算，普通墨粉通常也可以。不要用喷墨打印机，墨水会晕染，遇水会被冲掉。
- 正式使用前，带一张样张到银行，请他们核验 MICR 行。

## 隐私

`config.json`（含账号）、`checks/`（每张 PDF 的 MICR 行都印着账号）和签名图片都属于隐私信息。
`.gitignore` 已经排除了它们以及所有 `*.pdf` 文件。签名文件请命名为 `signature.png` 或 `signature_*.png`，
这样也会被忽略。注意：设置了签名图片后，任何能运行这个程序的人都能打出带签名的支票。

## 文件说明

| 文件 | 用途 |
|---|---|
| `app.py` | Windows 图形界面（tkinter） |
| `make_check.py` | 支票版面、MICR、登记簿和命令行 |
| `config.example.json` | `config.json` 的模板 |
| `requirements.txt` | Python 依赖（reportlab、Pillow） |
| `build_exe.bat`、`build_from_wsl.sh` | 打包 `CheckPrinter.exe` |
| `fonts/` | GnuMICR E-13B 字体及其许可证 |
| `icon.ico` | 程序图标 |

## 常见问题

| 问题 | 解决办法 |
|---|---|
| `routing_number ... fails the ABA checksum` | 有数字抄错了，请对照现有支票重新输入 |
| “Can't write the PDF” | 该 PDF 正在阅读器中打开，关闭后重试 |
| 打印出来偏小或错位 | 按实际大小 / 100% 打印，然后校准 |
| `build_exe.bat` 提示找不到带 tkinter 的 Windows Python | 从 python.org 安装 Python，并勾选 “Add python.exe to PATH” |
| 提示 “MICR font not found” | 复制完整的 `CheckPrinter` 文件夹，包括 `fonts\` |
