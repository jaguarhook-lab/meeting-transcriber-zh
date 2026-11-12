# Third-Party Notices（第三方套件授權聲明）

本程式原始碼以 MIT 授權發布（見 `LICENSE`）。
Releases 中的打包版（`錄音轉文字.exe` 與 `_internal\`）另外包含下列第三方元件，各依其授權條款散布。
各元件的完整授權文字可於下列專案網址取得；打包版 `_internal\` 內各 `*.dist-info` 資料夾亦附有原始授權檔。

語音模型（Whisper 權重）**不包含**在本程式中，由使用者自行從 Hugging Face 下載（OpenAI Whisper，MIT 授權）。

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

## AGPL 元件說明（PyMuPDF）

打包版用 PyMuPDF 把會議記錄轉成 PDF。PyMuPDF 與 MuPDF 以 AGPL-3.0 授權，因此**散布打包版時，打包版整體依 AGPL-3.0 條款提供**：
本程式完整原始碼即本專案儲存庫，PyMuPDF 原始碼見上表網址。只使用原始碼（MIT）而自行改用其他 PDF 方式者，不受此限。

## LGPL 元件說明

FFmpeg 與 chardet 以 LGPL 授權，本打包版以**獨立檔案**形式包含（FFmpeg 為 `_internal\av.libs\` 內的 DLL；chardet 為 `_internal\` 內的 Python 模組），使用者可自行以相容版本替換。
其原始碼可由上表網址取得。如需本打包版所使用版本的原始碼，請於本專案 GitHub Issues 提出，我們將提供取得方式。

## 商標

Claude、Claude Code 為 Anthropic 的商標；Codex、ChatGPT 為 OpenAI 的商標。本程式與上述公司無關，僅呼叫使用者自行安裝的命令列工具。
