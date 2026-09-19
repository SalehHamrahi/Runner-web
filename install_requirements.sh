#!/bin/bash

set -e

GREEN='\033[0;32m'
NC='\033[0m'

python3 -m venv .venv

source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

echo -e "${GREEN}Installation completed successfully!${NC}"