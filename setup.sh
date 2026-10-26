#!/usr/bin/env bash
# One-time setup on a new Mac: tools, Python + Node deps, and the Whisper model.
# The model (574 MB) is too big for git (GitHub caps files at 100 MB), so it is
# downloaded from the official whisper.cpp model repo and checked by SHA-1.
set -euo pipefail
cd "$(dirname "$0")"

MODEL=ggml-large-v3-turbo-q5_0.bin
MODEL_SHA1=e050f7970618a659205450ad97eb95a18d69c9ee
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$MODEL"

echo "1/4 tools (Homebrew): ffmpeg, whisper-cpp"
command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
for pkg in ffmpeg whisper-cpp; do
  brew list --versions "$pkg" >/dev/null || brew install "$pkg"
done

echo "2/4 python: numpy"
python3 -c "import numpy" 2>/dev/null || python3 -m pip install --user numpy

echo "3/4 node: remotion + dashboard"
npm --prefix remotion install

echo "4/4 whisper model: $MODEL"
mkdir -p montage/models
dest="montage/models/$MODEL"
if [[ -f "$dest" ]] && [[ "$(shasum -a 1 "$dest" | cut -d' ' -f1)" == "$MODEL_SHA1" ]]; then
  echo "    already there"
else
  curl -L --fail --progress-bar -o "$dest.part" "$MODEL_URL"
  got="$(shasum -a 1 "$dest.part" | cut -d' ' -f1)"
  [[ "$got" == "$MODEL_SHA1" ]] || { echo "    checksum mismatch ($got) — not using it"; rm -f "$dest.part"; exit 1; }
  mv "$dest.part" "$dest"
fi

echo "done — run: npm --prefix remotion run studio"
