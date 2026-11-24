#!/bin/sh
# Builds Quick Capture for both Apple architectures into dist/<electron arch>/, where the desktop app's
# electron-builder config picks the one for each DMG (desktop/package.json, mac.extraResources).
set -eu
cd "$(dirname "$0")"
channel=$(sed -n 's/^channel = "\(.*\)"/\1/p' rust-toolchain.toml)
rustup toolchain install "$channel" --profile minimal --target aarch64-apple-darwin --target x86_64-apple-darwin
for pair in aarch64-apple-darwin:arm64 x86_64-apple-darwin:x64; do
  target=${pair%%:*}
  arch=${pair##*:}
  cargo build --release --locked --target "$target"
  mkdir -p "dist/$arch"
  cp "${CARGO_TARGET_DIR:-target}/$target/release/paperlab-capture" "dist/$arch/paperlab-capture"
done
