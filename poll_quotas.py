#!/usr/bin/env python

import os
import logging
import datetime

import requests
import elasticsearch
import elasticsearch.helpers
from requests_oauthlib import OAuth2Session
import marshmallow as ma

logging.basicConfig(level=logging.INFO)

max_int = 2 ** 31 - 1


class Config(ma.Schema):
    es_uri = ma.fields.Str(load_from='ES_URI', required=True)
    poll_index = ma.fields.Str(load_from='POLL_QUOTA_INDEX', required=True)
    poll_doc_type = ma.fields.Str(load_from='POLL_DOC_TYPE', required=True)
    cf_api_url = ma.fields.Str(load_from='CF_API_URL', required=True)
    cf_client_id = ma.fields.Str(load_from='CF_CLIENT_ID', required=True)
    cf_client_secret = ma.fields.Str(load_from='CF_CLIENT_SECRET', required=True)


def get_session(api_url, client_id, client_secret):
    info = requests.get('{}/v2/info'.format(api_url))
    info.raise_for_status()

    token = requests.post(
        '{}/oauth/token'.format(info.json()['token_endpoint']),
        auth=(client_id, client_secret),
        data={'grant_type': 'client_credentials', 'response_type': 'token'},
    )
    token.raise_for_status()

    return OAuth2Session(client_id, token=token.json())


def poll_quotas(session, client, poll_index, doc_type):
    now = datetime.datetime.now()
    orgs = {
        org['metadata']['guid']: org
        for org in fetch(session, '/v2/organizations')
    }
    quotas = {
        quota['metadata']['guid']: quota
        for quota in fetch(session, '/v2/quota_definitions')
    }
    elasticsearch.helpers.bulk(
        client,
        get_poll_docs(orgs, quotas, now),
        index=poll_index,
        doc_type=doc_type,
    )


def get_poll_docs(orgs, quotas, now):
    for org in orgs.values():
        quota_guid = org['entity']['quota_definition_guid']
        quota = quotas[quota_guid]
        doc = {
            '_id': '{}-{}-{}'.format(
                org['metadata']['guid'],
                quota['metadata']['guid'],
                now.strftime('%Y-%m-%dT%H:%M:%S'),
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
    config, errors = Config().load(os.environ)
    if errors:
        print("The following environment variables must be set correctly to continue:")

        for what, err in errors.items():
            print("\t{0}: {1}".format(what, " ".join(err)))

        raise SystemExit(99)

    client = elasticsearch.Elasticsearch([config['es_uri']])
    session = get_session(
        config['cf_api_url'], config['cf_client_id'], config['cf_client_secret'])

    poll_quotas(
        session,
        client,
        config['poll_index'],
        config['poll_doc_type'],
    )
