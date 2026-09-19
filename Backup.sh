#!/bin/bash

rm -rf Backup

mkdir -p Backup/
mkdir -p Backup/Logs/
mkdir -p Backup/LogsJSON/
mkdir -p Backup/Results_analysis/


cp Logs/*.rc* Backup/Logs/ -v -r
cp Analyzer/LogsJSON/*.json Backup/LogsJSON/ -r -v
cp Analyzer/Results_analysis Backup/ -r -v