#!/bin/bash
cd "$(dirname "$0")"
ryu-manager --verbose controller.py 2>&1 | grep --line-buffered -E "EVENT|ERROR|Traceback|instantiating|Error"
