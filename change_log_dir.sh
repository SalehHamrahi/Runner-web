#!/bin/bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$ROOT_DIR/Logs"

shopt -s nullglob
files=("$ROOT_DIR"/*.rcg "$ROOT_DIR"/*.rcl)
if (( ${#files[@]} == 0 )); then
    exit 0
fi

for file in "${files[@]}"; do
    cp -- "$file" "$ROOT_DIR/Logs/"
done
