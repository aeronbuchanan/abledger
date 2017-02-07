#!/usr/bin/python3
#
# Read kraken ledger csv file and convert to 'raw' format read by abledger.py
#
# Filenames are hard-coded, so only directory can be given
#
# File format should be csv with headings on first line:
# "txid","refid","time","type","aclass","asset","amount","fee","balance"

import os
import argparse
import time
import csv
import re

os.environ['TZ'] = 'UTC' # workaround for no inverse of time.gmtime(t) 
TOLERANCE = 1e-6

parser = argparse.ArgumentParser()

parser.add_argument('-d', '--directory', help='dir for csv files to read', default='/home/aeron/Documents/Admin/Consensus Platform Trading/Trading Logs/Kraken/')

args = parser.parse_args()

def extractCSVs(_s, _n, _i):
  # TODO: pass error up instead of passing line number down
  line = _s.rstrip().lstrip()
  if line == '':
    return []
  for e in csv.reader([line], quotechar='"', delimiter=',', quoting=csv.QUOTE_ALL, skipinitialspace=True):
    vs = e
  if len(vs) != _n:
    sys.exit('ERROR: Incorrect number of entries on line %d (expecting %d, got %d)' % (_i, _n, len(vs)))
    sys.exit('parse error')
  return vs

currencyTranslation = {
  "ZEUR": "EUR",
  "ZUSD": "USD",
  "ZGBP": "GBP",
  "XETH": "ETH",
  "XXBT": "BTC",
  "XETC": "ETC",
  "XXLM": "XLM",
}

output = open(args.directory + 'kraken.transfers.csv', 'w')
output.write("Date, Base Currency, Value, Trade Currency, Amount, Transfer Info\n")

with open(args.directory + 'ledgers.csv') as f:
  ln = 0
  for line in f:
    ln += 1

    if ln == 1:
      if line.rstrip() != '"txid","refid","time","type","aclass","asset","amount","fee","balance"': 
        exit('ERROR: first line of "%s" not headings as expected' % inputfile)
    else:
      entries = extractCSVs(line, 9, ln)
      if entries:
        (txid, refid, timestr, type_, aclass, currency, amount, fee, balance) = entries
        if currency != "KFEE" and (type_ == 'deposit' or type_ == 'withdrawal' or type_ == 'transfer'):
          date = time.strftime('%Y-%m-%d-%H-00', time.strptime(timestr, '%Y-%m-%d %H:%M:%S'))
          currency = currencyTranslation[currency]
          amount = float(amount)
          if type_ == 'deposit': output.write("%s, %s, %f, %s, %f, ->kraken\n" % (date, currency, -amount, currency, amount))
          elif type_ == 'withdrawal': output.write("%s, %s, %f, %s, %f, ->kraken\n" % (date, currency, -amount, currency, amount))
          elif type_ == 'transfer': output.write("%s, GBP, 0, %s, %s,\n" % (date, currency, amount))
          else: exit("ERROR: unexpected ledger entry type '%s' slipped through!" % type_)

          fee = abs(float(fee))
          if fee > 0:
            output.write("%s, GBP, 0, %s, %f, \n" % (date, currency, -fee))

output.close()




