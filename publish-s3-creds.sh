#!/bin/bash

set -e -u -x

cf api "${CF_API_URL}"
(set +x; cf auth "${CF_USERNAME}" "${CF_PASSWORD}")

cf target -o ${CF_ORG} -s ${CF_SPACE}

JSON=$(cat  terraform-yaml/*.yml | spruce json | jq -r "{
    \"username\": .terraform_outputs.${S3_USER}_username,
    \"access_key_id\": .terraform_outputs.${S3_USER}_access_key_id_curr,
    \"secret_access_key\": .terraform_outputs.${S3_USER}_secret_access_key_curr,
    \"bucket\": \"${S3_BUCKET}\",
    \"region\": .terraform_outputs.vpc_region
}")

cf cups ${CF_UPS_NAME} -p "${JSON}" || cf uups ${CF_UPS_NAME} -p "${JSON}"
