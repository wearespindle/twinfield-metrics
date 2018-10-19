# Twinfield metrics

This script collects all monthly ledger data from Twinfield and put it in Influx. This makes it possible to create a monthly balance sheet. It will fetch all ledger data from the current year and last year if the current month is before March.

The script can be run at any time; it will add or replace datapoints on the first of the month. Recommended is to run this script daily, so all changes of previous periods or the current period will be pushed to Influx.
