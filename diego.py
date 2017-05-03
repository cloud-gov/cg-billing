#!/usr/bin/env python

import os
import time
import logging
import datetime

import requests
import schedule
import elasticsearch
import elasticsearch.helpers

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


def summarize(client, out_index, doc_type):
    date = datetime.date.today()
    date = date.replace(month=date.month - 1)
    if date.day == 1:
        try:
            in_index = 'logs-app-{}.*'.format(date.strftime('%Y.%m'))
            res = client.search(index=in_index, body=query)
            elasticsearch.helpers.bulk(
                client,
                get_bulk_docs(res, date),
                index=out_index,
                doc_type=doc_type,
            )
        except Exception:
            notify_slack('Failed to aggregate Diego metrics')
            raise
        notify_slack('Successfully aggregated Diego metrics')


def notify_slack(text):
    requests.post(
        os.environ['SLACK_URL'],
        json={
            'username': os.environ['SLACK_USERNAME'],
            'channel': os.environ['SLACK_CHANNEL'],
            'icon_url': os.environ['SLACK_ICON_URL'],
            'text': text,
        },
    ).raise_for_status()


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


if __name__ == '__main__':
    client = elasticsearch.Elasticsearch([os.environ['ES_URI']])
    index = os.environ['BILL_INDEX']
    doc_type = os.environ['DOC_TYPE']

    schedule.every().day.do(summarize, client, index, doc_type)

    while True:
        schedule.run_pending()
        time.sleep(1)
