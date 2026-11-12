# Third-Party Notices（第三方套件授權聲明）

本程式的程式碼採 MIT 授權（見 `LICENSE`）。

GitHub Releases 上的 Windows 打包版（`meeting-transcriber-zh-vX.Y.Z-win64.zip`）包含下列第三方元件，各自依其授權使用，原始授權檔在 `_internal\` 下各個 `*.dist-info` 資料夾裡。從原始碼執行或用 `build.py` 打包時也會用到這些元件；自行打包後散布給別人的話，請遵守它們的授權，特別是下面的 AGPL 與 LGPL 說明。

語音模型（OpenAI Whisper，MIT 授權）沒有包含在內，使用者自行從 Hugging Face 下載。

| 元件 | 授權 | 專案網址 |
|---|---|---|
| Python 3 執行環境 | PSF License | https://www.python.org |
| Tcl/Tk（tkinter） | Tcl/Tk License（BSD 類） | https://www.tcl.tk |
| faster-whisper（含 Silero VAD 模型） | MIT | https://github.com/SYSTRAN/faster-whisper |
| CTranslate2 | MIT | https://github.com/OpenNMT/CTranslate2 |
| ONNX Runtime | MIT | https://github.com/microsoft/onnxruntime |
| PyAV | BSD-3-Clause | https://github.com/PyAV-Org/PyAV |
| FFmpeg（PyAV 內附的動態連結程式庫 `av.libs\*.dll`） | LGPL-2.1-or-later | https://ffmpeg.org — 原始碼：https://ffmpeg.org/download.html |
| dav1d（PyAV 內附） | BSD-2-Clause | https://code.videolan.org/videolan/dav1d |
| tokenizers | Apache-2.0 | https://github.com/huggingface/tokenizers |
| huggingface_hub、hf_xet | Apache-2.0 | https://github.com/huggingface/huggingface_hub |
| NumPy（含 OpenBLAS 等） | BSD-3-Clause | https://numpy.org |
| opencc-python-reimplemented | Apache-2.0 | https://github.com/yichen0831/opencc-python |
| PyMuPDF（含 MuPDF） | AGPL-3.0（或 Artifex 商業授權） | https://github.com/pymupdf/PyMuPDF |
| Python-Markdown | BSD-3-Clause | https://github.com/Python-Markdown/markdown |
| requests | Apache-2.0 | https://github.com/psf/requests |
| urllib3 | MIT | https://github.com/urllib3/urllib3 |
| certifi | MPL-2.0 | https://github.com/certifi/python-certifi |
| charset-normalizer | MIT | https://github.com/jawah/charset_normalizer |
| chardet | LGPL-2.1-or-later | https://github.com/chardet/chardet |
| idna | BSD-3-Clause | https://github.com/kjd/idna |
| tqdm | MPL-2.0 與 MIT | https://github.com/tqdm/tqdm |
| PyYAML | MIT | https://github.com/yaml/pyyaml |
| filelock | Unlicense | https://github.com/tox-dev/filelock |
| fsspec | BSD-3-Clause | https://github.com/fsspec/filesystem_spec |
| packaging | Apache-2.0 或 BSD-2-Clause | https://github.com/pypa/packaging |
| click、itsdangerous、MarkupSafe | BSD-3-Clause | https://palletsprojects.com |
| attrs | MIT | https://github.com/python-attrs/attrs |
| multidict、yarl、propcache | Apache-2.0 | https://github.com/aio-libs |
| setuptools | MIT | https://github.com/pypa/setuptools |
| pywin32 | PSF License | https://github.com/mhammond/pywin32 |
| PyInstaller bootloader | GPL-2.0-or-later（含允許散布非 GPL 程式的例外條款） | https://pyinstaller.org |

## AGPL（PyMuPDF）

會議記錄轉 PDF 用的是 PyMuPDF，PyMuPDF 和 MuPDF 都採 AGPL-3.0 授權。因為打包版包含 PyMuPDF，整個作品的對應原始碼如下：

- 本專案：https://github.com/jaguarhook-lab/meeting-transcriber-zh ，和打包版同名的標籤（例如 `v1.1.2`）就是那一版的完整原始碼。
- PyMuPDF 1.27.2.2（MuPDF 1.27.2）：https://github.com/pymupdf/PyMuPDF/releases/tag/1.27.2.2 ，MuPDF 原始碼在 https://mupdf.com/releases
- 建置方式：Python 3.14 和 PyInstaller 6.22.3，執行 `build.py`，套件版本見 `requirements.txt`。

自行打包散布時，也請用同樣的方式提供對應原始碼。

## LGPL（FFmpeg、chardet）

FFmpeg 和 chardet 採 LGPL 授權，在打包版裡是獨立的檔案，可以換成相容的版本：FFmpeg 是 `_internal\av.libs\` 裡的 DLL，隨 PyAV 18.1.0 附帶；chardet 是 `_internal\` 裡的 Python 模組。原始碼可從上表的網址取得，PyAV 在 https://github.com/PyAV-Org/PyAV/releases/tag/v18.1.0 。

## 商標

Claude、Claude Code 是 Anthropic 的商標；Codex、ChatGPT 是 OpenAI 的商標。本程式與這兩家公司無關，只是呼叫使用者自己安裝的命令列工具。
