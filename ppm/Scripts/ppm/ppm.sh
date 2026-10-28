#!/bin/sh
cd REPLACE_WITH_PATH & python3 -m ppm $@ & cd $(dirname "$(dirname "$(readlink -f "$0")")")


