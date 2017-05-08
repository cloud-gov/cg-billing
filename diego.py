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


def get_date(value=None):
    """Return a datetime object for the first day of the current month
    or the year/month specified in `value`

    Args:
        value(str): "YYYY-MM" specifiying the year and month

    Returns:
        datetime.datetime
    """
    if value:
        year, month = value.split('-')
        return datetime.datetime(int(year), int(month), 1)
    today = datetime.date.today()
    return today.replace(day=1) - dateutil.relativedelta.relativedelta(months=1)


if __name__ == '__main__':
    es_uri = os.environ.get('ES_URI')
    bill_index = os.environ.get('BILL_INDEX')
    doc_type = os.environ.get('DOC_TYPE')

    if es_uri is None or bill_index is None or doc_type is None:
        print("The following environment variables must be set to continue:")
        print("\tES_URI - A URI to an elasticsearch instance")
        print("\tBILL_INDEX - The name of the index to store results in")
        print("\tDOC_TYPE - The document type used in BILL_INDEX")

        raise SystemExit(99)

    client = elasticsearch.Elasticsearch([es_uri])
    summarize(
        client,
        get_date(os.environ.get('DATE')),
        bill_index,
        doc_type,
    )
