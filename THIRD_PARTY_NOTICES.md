# Third-Party Notices（第三方套件授權聲明）

本程式原始碼以 MIT 授權發布（見 `LICENSE`）。
GitHub Releases 提供打包好的 Windows 版（`meeting-transcriber-zh-vX.Y.Z-win64.zip`，v1.1.1 起），內含下列第三方元件，各依其授權條款使用；
打包資料夾 `_internal\` 內各 `*.dist-info` 資料夾附有原始授權檔。從原始碼執行或用 `build.py` 自行打包時，也會使用這些元件。
**若你把自行打包的版本散布給他人**，須自行遵守下列各元件的授權條款（特別是下方 AGPL、LGPL 說明）。

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

本程式用 PyMuPDF 把會議記錄轉成 PDF。PyMuPDF 與 MuPDF 以 AGPL-3.0 授權。
本專案自有程式碼以 MIT 授權；Releases 的打包版包含 PyMuPDF，依 AGPL-3.0 提供整體作品的對應原始碼：

- **本專案原始碼**：https://github.com/jaguarhook-lab/meeting-transcriber-zh ，與打包版同名的標籤（例如 `v1.1.1`）即為該版本的完整原始碼。
- **PyMuPDF 1.27.2.2（MuPDF 1.27.2）**：https://github.com/pymupdf/PyMuPDF/releases/tag/1.27.2.2 ；MuPDF 原始碼：https://mupdf.com/releases
- **建置方式**：Python 3.14、PyInstaller 6.22.3，執行原始碼中的 `build.py`（套件版本見 `requirements.txt`）。

自行打包並散布給他人時，請以同樣方式提供你的對應原始碼。

## LGPL 元件說明

FFmpeg 與 chardet 以 LGPL 授權。打包版以**獨立檔案**形式包含（FFmpeg 為 `_internal\av.libs\` 內的 DLL，隨 PyAV 18.1.0 提供；chardet 為 `_internal\` 內的 Python 模組），可自行以相容版本替換。
其原始碼可由上表網址取得（PyAV：https://github.com/PyAV-Org/PyAV/releases/tag/v18.1.0 ）。

## 商標

Claude、Claude Code 為 Anthropic 的商標；Codex、ChatGPT 為 OpenAI 的商標。本程式與上述公司無關，僅呼叫使用者自行安裝的命令列工具。
