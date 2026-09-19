#!/bin/bash

GREEN='\033[0;32m'
NC='\033[0m'

if ! command -v loganalyzer &> /dev/null; then
    git clone https://github.com/Farzin-Negahbani/Namira-LogAnalyzer.git
    cd Namira-LogAnalyzer
    sudo apt-get update
    sudo apt-get python3 python3-pip python3-setuptools python3-numpy python3-matplotlib
    sudo python3 ./setup.py install
    cd ..
    sudo rm -rf Namira-LogAnalyzer

    echo -e "${GREEN}Installation completed successfully!${NC}"
fi