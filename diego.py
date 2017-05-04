#!/usr/bin/env python

import os
import logging
import datetime

import elasticsearch
import elasticsearch.helpers
import dateutil.relativedelta

logging.basicConfig(level=logging.INFO)

metrics = ['memory_bytes', 'memory_bytes_quota']

max_int = 2 ** 31 - 1

aggs = {
    metric: {'sum': {'field': 'containermetric.{}'.format(metric)}}
    for metric in metrics
}
aggs.update({
    'orgs': {'terms': {'field': '@cf.org'}}
})

query = {
    'size': 0,
    'query': {
        'bool': {
            'filter': [
                {'type': {'value': 'ContainerMetric'}}
            ],
        },
    },
    'aggs': {
        'org': {
            'terms': {'field': '@cf.org_id', 'size': max_int},
            'aggs': aggs,
        },
    },
}


def summarize(client, date, out_index, doc_type):
    in_index = 'logs-app-{}.*'.format(date.strftime('%Y.%m'))
    res = client.search(index=in_index, body=query)
    elasticsearch.helpers.bulk(
        client,
        get_bulk_docs(res, date),
        index=out_index,
        doc_type=doc_type,
    )


def get_bulk_docs(res, date):
    for org in res['aggregations']['org']['buckets']:
        doc = {
            '_id': '{}-{}'.format(date.strftime('%Y-%m'), org['key']),
            'org_id': org['key'],
            'date': date,
            'orgs': [each['key'] for each in org['orgs']['buckets']],
        }
        doc.update({metric: org[metric]['value'] for metric in metrics})
        logging.info(doc)
        yield doc


def get_date(value):
    if value:
        year, month = value.split('-')
        return datetime.datetime(int(year), int(month), 1)
    today = datetime.date.today()
    return today.replace(day=1) - dateutil.relativedelta.relativedelta(months=1)


if __name__ == '__main__':
    client = elasticsearch.Elasticsearch([os.environ['ES_URI']])
    summarize(
        client,
        get_date(os.getenv('DATE')),
        os.environ['BILL_INDEX'],
        os.environ['DOC_TYPE'],
    )
