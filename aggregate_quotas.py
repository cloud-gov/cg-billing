#!/usr/bin/env python

from calendar import monthrange
import os
import json
import logging
import datetime

import elasticsearch
import elasticsearch.helpers
from dateutil.relativedelta import relativedelta
import marshmallow as ma

from utils import Encoder

logging.basicConfig(level=logging.INFO)

max_int = 2 ** 31 - 1


class Config(ma.Schema):
    es_uri = ma.fields.Str(load_from='ES_URI', required=True)
    date = ma.fields.DateTime(
        load_from='DATE',
        format="%Y-%m",
        missing=(datetime.datetime.now() - relativedelta(months=1)).strftime('%Y-%m'),
    )
    poll_index = ma.fields.Str(load_from='POLL_QUOTA_INDEX', required=True)
    poll_doc_type = ma.fields.Str(load_from='POLL_DOC_TYPE', required=True)
    aggregate_index = ma.fields.Str(load_from='AGG_QUOTA_INDEX', required=True)
    aggregate_doc_type = ma.fields.Str(load_from='AGG_DOC_TYPE', required=True)
    out_dir = ma.fields.Str(load_from='OUT_DIR', missing=os.getcwd())


def aggregate_quotas(client, date, poll_index, agg_index, doc_type, out_dir):
    res = client.search(index=poll_index, body=get_aggregate_query(date))
    docs = list(get_aggregate_docs(res, date))

    # for each aggregate result, append the details used to generate that as the record
    for doc in docs:
        doc['daily_detail'] = client.mget(
            body={"ids":[
                "{0}-{1}-{2:02d}-{3:02d}".format(doc['org_id'], date.year, date.month, x)
                for x in range(1, monthrange(date.year, date.month)[1]+1)
            ]},
            index=poll_index,
            doc_type=doc_type
        )['docs']

    elasticsearch.helpers.bulk(
        client,
        docs,
        index=agg_index,
        doc_type=doc_type,
    )

    path = os.path.join(out_dir, 'quotas-{}.json'.format(date.strftime('%Y%m')))
    with open(path, 'w') as fp:
        json.dump(docs, fp, cls=Encoder)

def get_aggregate_query(date):
    gte = date.replace(day=1)
    lt = gte + relativedelta(months=1)

    return {
        'size': 0,
        'query': {
            'range': {
                '@timestamp': {
                    'gte': gte,
                    'lt': lt,
                },
            },
        },
        'aggs': {
            'org': {
                'terms': {'field': 'org_id.keyword', 'size': max_int},
                'aggs': {
                    'memory_limit': {'sum': {'field': 'memory_limit'}},
                    'quota_ids': {'terms': {'field': 'quota_id.keyword'}},
                    'org_names': {'terms': {'field': 'org_name.keyword'}},
                },
            },
        },
    }


def get_aggregate_docs(res, date):
    for org in res['aggregations']['org']['buckets']:
        doc = {
            '_id': '{}-{}'.format(date.strftime('%Y-%m'), org['key']),
            'date': date,
            'org_id': org['key'],
            'org_names': [each['key'] for each in org['org_names']['buckets']],
            'quota_ids': [each['key'] for each in org['quota_ids']['buckets']],
            'memory_limit': org['memory_limit']['value'],
        }
        logging.info(doc)
        yield doc


if __name__ == '__main__':
    config, errors = Config().load(os.environ)
    if errors:
        print("The following environment variables must be set correctly to continue:")

        for what, err in errors.items():
            print("\t{0}: {1}".format(what, " ".join(err)))

        raise SystemExit(99)

    client = elasticsearch.Elasticsearch([config['es_uri']])

    aggregate_quotas(
        client,
        config['date'],
        config['poll_index'],
        config['aggregate_index'],
        config['aggregate_doc_type'],
        config['out_dir'],
    )
