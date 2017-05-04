#!/bin/sh

set -e

billing_path=$(dirname $0)
pip install -r ${billing_path}/requirements.txt
${billing_path}/diego.py
