#!/usr/bin/env python

import datetime
import logging
import os

import elasticsearch
import elasticsearch.helpers
import marshmallow as ma


class Config(ma.Schema):
    es_uri = ma.fields.Str(load_from='ES_URI', required=True)
    date = ma.fields.DateTime(
        load_from='DATE',
        format="%Y-%m",
        missing=datetime.datetime.now().strftime('%Y-%m'),
    )
    bill_index = ma.fields.Str(load_from='BILL_INDEX', required=True)
    doc_type = ma.fields.Str(load_from='DOC_TYPE', required=True)


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
    """Perform aggreegate queries against a month of logsearch-for-cloudfoundry
    indexes and store the results in a another index.

    Args:
        client(elasticsearch.Elasticsearch): A configured elasticsearch client
        date(datetime.datetime): What year / month to query
        out_index(str): The index to store results in
        doc_type(str): The document type to store results in

    Returns:
        None

    Raises:
        http://elasticsearch-py.readthedocs.io/en/master/exceptions.html

    """
    in_index = 'logs-app-{}.*'.format(date.strftime('%Y.%m'))
    res = client.search(index=in_index, body=query, request_timeout=300)
    elasticsearch.helpers.bulk(
        client,
        get_bulk_docs(res, date),
        index=out_index,
        doc_type=doc_type,
    )


def get_bulk_docs(res, date):
    """A generator that returns formatted documents suitable for bulk indexing

    Args:
        res: Results from an es search
        date: What year / month the results are for

    Yields:
        dict: A document to store

    """
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
    config, errors = Config().load(os.environ)
    if errors:
        print("The following environment variables must be set correctly to continue:")

        for what, err in errors.items():
            print("\t{0}: {1}".format(what, " ".join(err)))

        raise SystemExit(99)

    print("Running with the following configuration:")
    for kk, vv in config.items():
        print("\t{0}: {1}".format(kk, vv))

    client = elasticsearch.Elasticsearch([config['es_uri']])
    summarize(
        client,
        config['date'],
        config['bill_index'],
        config['doc_type'],
    )
