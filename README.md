# cg-billing

## Diego
* Diego emits usage metrics per container every 15s via the firehose. These metrics are stored in elasticsearch as part of [logsearch](https://github.com/18F/cg-deploy-logsearch).
* On the first day of each month, the billing pipeline sums the container metrics by organization for the previous month. Aggregated container metrics are stored in elasticsearch and published to s3 for use by the customer team.
* Container memory reservation and usage are reported in bytes, and metrics are emitted every 15s, so to convert summed memory values to GB * day units, divide by 4 events / minute * 60 minutes / hour * 24 hours / day / 1024 bytes / KB / 1024 KB / MB / 1024 MB / GB.

## Quotas
* The billing concourse pipeline tracks daily quota requests for all organizations (we poll quota requests hourly to ensure that skipping a poll doesn't cause us to lose data, but we only keep the last result for each day). Daily quota requests are stored in elasticsearch.
* On the first day of each month, the billing pipeline sums the daily quota requests by organization for the previous month. Aggregated quota requests are stored in elasticsearch and published to s3 for use by the customer team.
* Quota reservations are reported in MB, so to convert summed memory values to GB * day units, divide by 1024 MB / GB.

## Accessing data
Summarized diego and quotas data are published to s3 on the first day of the month. Read-only access credentials for the s3 bucket are automatically published to a user-provided service in an organization and space specified by the customer team.
