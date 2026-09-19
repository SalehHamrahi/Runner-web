#!/bin/bash

mkdir .tmp
cp *.rc* .tmp

for file in ./*.tar.gz; do
    if [ -f "$file" ]; then
	tar xvf "$file"
	rm "$file"
    fi
done

mv .tmp/* .
rm .tmp -rf
