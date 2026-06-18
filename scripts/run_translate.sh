#!/bin/bash
# Activate venv and run translate script

cd ~/scripts
source .venv/bin/activate
python translate.py "$@"
deactivate
