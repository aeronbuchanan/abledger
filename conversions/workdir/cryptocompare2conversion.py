#!/usr/bin/python3
#
# Convert cryptocompare's multi-currency api download to conversion files

import time
import sys
import os
import glob
import argparse
import re

os.environ['TZ'] = 'UTC' # workaround for no inverse of time.gmtime(t) 
TOLERANCE = 1e-6
FLOAT_ZERO = 1e-8

parser = argparse.ArgumentParser()
parser.add_argument("-i", "--input", help="csv file(s) to read", default="cryptocompare*.csv")
args = parser.parse_args()

inputs = glob.glob(args.input)

if len(inputs) == 0:
  sys.exit('need input csv(s)')

# 2017-01-25 18:00,{"ETC":{"BTC":0.001428,"USD":1.28,"EUR":1.2}}
perform = re.compile('(.+?),{"(\w{3})":{"(\w{3})":(.+?),"(\w{3})":(.+?),"(\w{3})":(.+?)}}')

for filename in inputs:
  print("Reading '%s'..." % (filename))

  with open(filename) as f:
    ln = 0
    prices = [0, 0, 0]
    toCurrencies = ['', '', '']
    outfiles = []

    for line in f:
      ln += 1

      entries = perform.match(line)
      if entries == None:
        print("WARNING: no match on line %d" % ln) 
        continue

      #print("DEBUG: " + str(entries.groups()))

      timestr = entries.group(1)
      fromCurrency = entries.group(2)
      toCurrencies[0] = entries.group(3)
      prices[0] = float(entries.group(4))
      toCurrencies[1] = entries.group(5)
      prices[1] = float(entries.group(6))
      toCurrencies[2] = entries.group(7)
      prices[2] = float(entries.group(8))

      date = time.strftime("%Y-%m-%d-%H-%M", time.strptime(timestr, "%Y-%m-%d %H:%M"))

      if any(p == 0 for p in prices):
        print("WARNING: zero price detected on line %d. Stopping" % ln)
        break

      if ln == 1:
        for toCurrency in toCurrencies:
          outfile = open('cc' + fromCurrency + toCurrency + ".csv", 'w')
          outfile.write("%s, %s\n" % (fromCurrency, toCurrency))
          outfiles.append(outfile)

      for i in range(0, 3):
        outfiles[i].write("%s, %s\n" % (date, prices[i]))

    for outfile in outfiles:
      outfile.close()



