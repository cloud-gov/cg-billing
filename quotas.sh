#!/bin/sh

set -e

billing_path=$(dirname $0)
pip install -r ${billing_path}/requirements.txt
if [ "${ACTION}" = "poll" ]; then
  ${billing_path}/poll_quotas.py
elif [ "${ACTION}" = "aggregate" ]; then
  ${billing_path}/aggregate_quotas.py
fi
