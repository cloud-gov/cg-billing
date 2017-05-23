#!/bin/bash

set -e -u -x

billing_path=$(dirname $0)
pip3 install -r "${billing_path}/requirements.txt"

org="${ORG:-"test-quotas-${RANDOM}"}"
quota="${QUOTA:-"test-quotas-${RANDOM}"}"
poll_index="${POLL_QUOTA_INDEX:-"test-poll-quotas-${RANDOM}"}"
agg_index="${POLL_QUOTA_INDEX:-"test-aggregate-quotas-${RANDOM}"}"

cf api "${CF_API_URL}"
(set +x; cf auth "${CF_USERNAME}" "${CF_PASSWORD}")

cf create-org "${org}"
cf create-quota "${quota}" -m 512M
cf set-quota "${org}" "${quota}"

guid=$(cf org "${org}" --guid)

# emit day at 512M
TEST_QUOTA_DATE="1972-05-21" POLL_QUOTA_INDEX="${poll_index}" python3 "${billing_path}/poll_quotas.py"

# quota changed, this should overwrite the current date
cf update-quota "${quota}" -m 1024M
TEST_QUOTA_DATE="1972-05-21" POLL_QUOTA_INDEX="${poll_index}" python3 "${billing_path}/poll_quotas.py"

# fake some more data for the next day to test aggregates
TEST_QUOTA_DATE="1972-05-22" POLL_QUOTA_INDEX="${poll_index}" python3 "${billing_path}/poll_quotas.py"


# Wait for result
elapsed=300
until [ "${elapsed}" -le 0 ]; do
  res=$(curl "${ES_URI}/${poll_index}/_search?q=org_name.keyword:${org}")
  total=$(echo "${res}" | jq -r '.hits.total')
  if [[ "${total}" -eq 2 ]]; then
    break
  fi
  let elapsed-=15
  sleep 15
done

if [[ "${total}" -ne 2 ]]; then
  echo "Expected 2 hits; got ${total}"
  exit 1
fi

limit=$(echo "${res}" | jq -r '.hits.hits[0]._source.memory_limit')
if [[ "${limit}" -ne 1024 ]]; then
  echo "Expected 1024 limit; got ${limit}"
  exit 1
fi

# Test aggregates
doc_id="1972-05-${guid}"

elapsed=600
until [ "${elapsed}" -le 0 ]; do
  DATE="1972-05" POLL_QUOTA_INDEX="${poll_index}" AGG_QUOTA_INDEX="${agg_index}" python3 "${billing_path}/aggregate_quotas.py"
  doc=$(curl "${ES_URI}/${agg_index}/${AGG_DOC_TYPE}/${doc_id}")
  found=$(echo "${doc}" | jq -r '.found')
  if [[ "${found}" = "true" ]]; then
    break
  fi
  let elapsed-=60
  sleep 60
done

if [[ "${found}" = "false" ]]; then
  echo "Aggregate document with _id ${doc_id} not found"
  exit 1
fi

observed=$(echo "${doc}" | jq -r '._source.memory_limit')
expected="2048"
if [[ "${observed}" -ne "${expected}" ]]; then
  echo "Expected aggregate value ${expected}; got ${observed}"
  exit 1
fi

observed=$(echo "${doc}" | jq -r '._source.daily_detail | length')
expected="31" # number of days in may, our test month
if [[ "${observed}" -ne "${expected}" ]]; then
  echo "Expected ${expected} days of detail; got ${observed}"
  exit 1
fi

observed=$(echo "${doc}" | jq -r '[._source.daily_detail[] | select(.found)] | length')
expected="2" # number of days in may, with actual data
if [[ "${observed}" -ne "${expected}" ]]; then
  echo "Expected ${expected} days of valid data in detail; got ${observed}"
  exit 1
fi


# Cleanup
cf delete-org -f "${org}"
cf delete-quota -f "${quota}"
curl -X DELETE "${ES_URI}/${poll_index}"
curl -X DELETE "${ES_URI}/${agg_index}"
