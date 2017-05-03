#!/usr/bin/env python

import os
import time
import logging
import datetime

import schedule
import elasticsearch
import elasticsearch.helpers

logging.basicConfig(level=logging.INFO)

metrics = ['memory_bytes', 'memory_bytes_quota']

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
            'terms': {'field': '@cf.org', 'size': 500},
            'aggs': {
                metric: {'avg': {'field': 'containermetric.{}'.format(metric)}}
                for metric in metrics
            },
        },
    },
}


def summarize(client, out_index, doc_type):
    date = datetime.date.today()
    if date.day == 1:
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
        yield {
            'update': {
                '_id': '{}-{}'.format(date.strftime('%Y-%m'), org['key']),
            },
        }
        doc = {'org': org['key'], 'date': date.strftime('%Y-%m-%d')}
        doc.update({metric: org[metric]['value'] for metric in metrics})
        logging.info(doc)
        yield {'doc': doc}


if __name__ == '__main__':
    client = elasticsearch.Elasticsearch([os.environ['ES_URI']])
    index = os.environ['BILL_INDEX']
    doc_type = os.environ['DOC_TYPE']

    schedule.every().minute.do(summarize, client, index, doc_type)

    while True:
        schedule.run_pending()
        time.sleep(1)
