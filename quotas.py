#!/usr/bin/env python

import os
import logging
import datetime

import requests
import elasticsearch
import elasticsearch.helpers
from requests_oauthlib import OAuth2Session

logging.basicConfig(level=logging.INFO)


def get_session():
    info = requests.get('{}/v2/info'.format(os.environ['CF_API_URL']))
    info.raise_for_status()

    token = requests.post(
        '{}/oauth/token'.format(info.json()['token_endpoint']),
        auth=(os.environ['CF_CLIENT_ID'], os.environ['CF_CLIENT_SECRET']),
        data={'grant_type': 'client_credentials', 'response_type': 'token'},
    )
    token.raise_for_status()

    return OAuth2Session(os.getenv('CLIENT_ID'), token=token.json())


def emit_quotas(session, client, index, doc_type):
    now = datetime.datetime.now()
    orgs = {
        org['entity']['quota_definition_guid']: org
        for org in fetch(session, '/v2/organizations')
    }
    quotas = {
        quota['metadata']['guid']: quota
        for quota in fetch(session, '/v2/quota_definitions')
    }
    elasticsearch.helpers.bulk(
        client,
        get_bulk_docs(orgs, quotas, now),
        index=index,
        doc_type=doc_type,
    )


def get_bulk_docs(orgs, quotas, now):
    for quota_guid, org in orgs.items():
        quota = quotas[quota_guid]
        doc = {
            '_id': '{}-{}'.format(
                quota['metadata']['guid'],
                now.strftime('%Y-%m-%dT%H:%M'),
            ),
            '@timestamp': now,
            'org_id': org['metadata']['guid'],
            'org_name': org['entity']['name'],
            'quota_id': quota['metadata']['guid'],
            'quota_name': quota['entity']['name'],
            'memory_limit': quota['entity']['memory_limit'],
        }
        logging.info(doc)
        yield doc


def fetch(session, url):
    while True:
        resp = session.get('{}/{}'.format(os.environ['CF_API_URL'], url))
        resp.raise_for_status()
        result = resp.json()
        for resource in result['resources']:
            yield resource
        url = result['next_url']
        if not url:
            break


if __name__ == '__main__':
    emit_quotas(
        get_session(),
        elasticsearch.Elasticsearch([os.environ['ES_URI']]),
        os.environ['QUOTA_INDEX'],
        os.environ['DOC_TYPE'],
    )
