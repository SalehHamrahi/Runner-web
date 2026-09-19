.PHONY: test quality release compile

PYTHON ?= python3

test:
	$(PYTHON) -m unittest discover -s tests -v

quality:
	./scripts/quality_check.sh

compile:
	$(PYTHON) -m compileall -q runner.py core web Analyzer group_generator.py table_generator.py

release:
	./scripts/release.sh
