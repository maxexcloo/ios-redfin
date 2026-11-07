#!/bin/sh
# Host regression tests for pd-mapper's QMI domain-list responses.
set -e
cd "$(dirname "$0")"
mkdir -p out
${CC:-cc} -O1 -g -Wall -Wextra -Wno-unused-parameter -ftrivial-auto-var-init=pattern -fsanitize=address,undefined -o out/test_pdmapper \
	test_pdmapper.c pdmapper.c qmi.c
./out/test_pdmapper
