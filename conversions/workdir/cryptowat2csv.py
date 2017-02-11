#!/usr/bin/python3
#
# Convert json from cryptowat.ch to simple conversion csv format

import os
import argparse
import json
import time

os.environ['TZ'] = 'UTC' # workaround for no inverse of time.gmtime(t) 

parser = argparse.ArgumentParser()

parser.add_argument("-i", "--input", help="json file to read", default="")
parser.add_argument("-o", "--output", help="filename of output file", default="")
parser.add_argument("-t", "--toCurrency", help="to currency symbol", default="")
parser.add_argument("-f", "--fromCurrency", help="from currency symbol", default="")

args = parser.parse_args()

f = open(args.input)
data = json.loads(f.readline())

outfile = open(args.output, 'w')
outfile.write("%s, %s\n" % (args.toCurrency, args.fromCurrency))

timeseries = list(data['result'].keys())
timeseries.sort()
timeseries.reverse()

prices = {}

for ts in timeseries:
  for entries in data['result'][ts]:
    # [ CloseTime, OpenPrice, HighPrice, LowPrice, ClosePrice, Volume ]
    date = time.strftime("%Y-%m-%d-%H-%M", time.gmtime(int(entries[0])))
    price = float(entries[4]) # use close price
    prices[date] = price  

dates = list(prices.keys())
dates.sort()

for date in dates:
  outfile.write("%s, %f\n" % (date, prices[date]))

outfile.close()
