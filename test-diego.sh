#!/bin/bash

set -e -u -x

billing_path=$(dirname $0)
pip3 install -r "${billing_path}/requirements.txt"

org="${ORG:-"test-billing-${RANDOM}"}"
space="${SPACE:-"test-billing"}"
index="${BILL_INDEX:-"test-billing-${RANDOM}"}"

cf api "${CF_API_URL}"
(set +x; cf auth "${CF_USERNAME}" "${CF_PASSWORD}")

cf create-org "${org}"
cf target -o "${org}"
guid=$(cf org "${org}" --guid)

cf create-space "${space}"
cf target -s "${space}"

cf push test-billing \
  -m 128M \
  -b binary_buildpack \
  -c 'sleep infinity' \
  --health-check-type process \
  --no-route

sleep 300

cf delete-org -f "${org}"

sleep 300

DATE="$(date +%Y-%m)" BILL_INDEX="${index}" python3 "${billing_path}/diego.py"

doc_id="$(date +%Y-%m)-${guid}"
doc=$(curl "${ES_URI}/${index}/${DOC_TYPE}/${doc_id}")

expected=$(( 5 * 4 * 1024 * 1024 * 128 ))  # 5 minutes * 4 metrics / minute * 1024 bytes / kb * 1024 kb / mb * 128 mb
observed=$(echo "${doc}" | jq -r '._source.memory_bytes_quota' | awk '{printf "%.0f", $1}')
ratio=$(( 100 * (expected - observed) / ((expected + observed) / 2) ))

if [ ${ratio#-} -gt 10 ]; then
  echo "Observed value ${observed} too different from expected value ${expected}"
  exit 1
fi

curl -X DELETE "${ES_URI}/${index}"
