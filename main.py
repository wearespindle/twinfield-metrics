import argparse
import datetime
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError
import json
from xml.dom.minidom import parseString

from twinfield import TwinfieldApi, render_to_string


# Json based config: jira credentials and Influx credentials
config_filepath = 'config.json'


def main(verbose=False):
    # Get the config file.
    with open(config_filepath) as json_config_file:
        config = json.load(json_config_file)
    
    now = datetime.datetime.now()
    current_year = now.year
    current_month = now.month
    month_data = {}
    twinfield_json = []
    
    # Get the ledger information from Twinfield.
    with TwinfieldApi(config['twinfield']) as conn:
        # If the year is before march, also get last year, as corrections may
        # have been done to the previous year.
        if current_month < 3:
            month_data.update(get_ledger(conn, current_year-1, 12, verbose))
        month_data.update(get_ledger(conn, current_year, current_month-1, verbose))

    # Create the json to send to influx.
    if verbose:
        print('----')
        print('Company result per month:')
    for key in month_data:
        twinfield_json.append({
            "measurement": "twinfield-ledger-accounts",
            "fields": month_data[key],
            "time": key
        })
        if verbose:
            yearmonth = month_data[key]
            total = 0
            for ledger_account in yearmonth:
                total += yearmonth[ledger_account]
            print('%s: %d' % (key, total))
    
    # Connect to the Influxdb.
    if verbose:
        print('----')
        print('Writing points to Influx')
    client = InfluxDBClient(
        config['influxdb']['host'],
        config['influxdb']['port'],
        config['influxdb']['user'],
        config['influxdb']['pass'],
        config['influxdb']['database'],
        timeout=10)
    # Write the Influx points.
    client.write_points(twinfield_json)        


def get_ledger(conn, year, month, verbose):
    # Get all ledger account numbers for the whole year, so we have already
    # have all account numbers.
    if verbose:
        print('Getting all ledger account numbers for %d' % year)
    ledger_account_xml = render_to_string('twinfield/xml/040_1.xml', context={"year":year})
    ledger_account_xml = conn.send(ledger_account_xml)
    ledger_account_xml = parseString(ledger_account_xml.text)
    values_to_save = []
    trs = ledger_account_xml.getElementsByTagName('tr')
    for tr in trs:
        tds = tr.childNodes
        for td in tds:
            save = None
            attributes = td.attributes            
            if not save and 'field' in attributes.keys() and attributes.get('field').value == 'fin.trs.line.dim1':
                if td.firstChild.nodeValue not in values_to_save:
                    values_to_save.append(td.firstChild.nodeValue)
                break
    values_to_save = sorted(values_to_save)

    # Get the ledger account amounts for all months within `year`, starting at
    # `month`.
    month_data = {}
    for i in range(1, month+1):
        # Initialize the dict for all possible ledger accounts with a 0.
        yearmonthdict = {key: 0 for key in values_to_save}
        # Create the yearmonth string
        yearmonth = "%d/%s" % (year, i >= 10 and str(i) or "0%d" % i)
        # Get the yearmonth data from Twinfield
        if verbose:
            print('Getting ledger account amounts for %s' % yearmonth)
        xml = render_to_string('twinfield/xml/030_1.xml', context={"yearmonth":yearmonth})
        xml = conn.send(xml)
        xml = parseString(xml.text)
        
        # For each row, save or add the amount to the yearmonthdict
        trs = xml.getElementsByTagName('tr')
        for tr in trs:
            tds = tr.childNodes
            for td in tds:
                save = None
                attributes = td.attributes            
                if 'field' in attributes.keys() and attributes.get('field').value == 'fin.trs.line.dim1':
                    if td.firstChild.nodeValue in values_to_save:
                        save = td.firstChild.nodeValue
                    break
            if save:
                for td in tds:
                    attributes = td.attributes
                    if 'field' in attributes.keys() and attributes.get('field').value == 'fin.trs.line.valuesigned':
                        yearmonthdict[save] += float(td.firstChild.nodeValue)
                        break

        # Round the amounts
        for key in yearmonthdict:
            yearmonthdict[key] = int(round(yearmonthdict[key]))
        
        # Save the amount with the timestamp of the month. This will be used
        # as influx key (which is always a date).
        timestamp = datetime.datetime.strptime("%s/01" % yearmonth, "%Y/%m/%d")
        month_data.update({str(timestamp): yearmonthdict})
    return month_data


def test():
    """
    Test all connections
    """
    with open(config_filepath) as json_config_file:
        config = json.load(json_config_file)    
    with TwinfieldApi(config['twinfield']) as conn:
        conn.change_office()
    client = InfluxDBClient(
        config['influxdb']['host'],
        config['influxdb']['port'],
        config['influxdb']['user'],
        config['influxdb']['pass'],
        config['influxdb']['database'],
        timeout=10)
    client.get_list_measurements()
    
    print('Everything looks good!')
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true', help='Prints the progress and the ledger totals.')
    parser.add_argument('-t', '--test', action='store_true', help='Test all connections.')
    args = parser.parse_args()
    if args.test:
        test()
    else:
        main(verbose=args.verbose)
