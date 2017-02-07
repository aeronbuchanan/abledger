#!/usr/bin/python3
#
# Read poloniex deposit and withdrawal csv files and convert to 'raw'
# format read by abledger.py
#
# Filenames are hard-coded, so only directory can be given
#
# File format should be csv with headings on first line:
# Date,Currency,Amount,Address,Status

import os
import argparse
import time
import csv
import re

os.environ['TZ'] = 'UTC' # workaround for no inverse of time.gmtime(t) 
TOLERANCE = 1e-6

parser = argparse.ArgumentParser()

parser.add_argument('-d', '--directory', help='dir for csv files to read', default='/home/aeron/Documents/Admin/Consensus Platform Trading/Trading Logs/Poloniex/')

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

reCheckERROR = re.compile('ERROR')
reCheckCOMPLETE = re.compile('COMPLETE')

output = open(args.directory + 'poloniex.transfers.csv', 'w')
output.write("Date, Base Currency, Value, Trade Currency, Amount, Transfer Info\n")

def writeTransfers(inputfile, outputFormat):
  with open(args.directory + inputfile) as f:
    ln = 0
    for line in f:
      ln += 1

      if ln == 1:
        if line.rstrip() != 'Date,Currency,Amount,Address,Status': 
          exit('ERROR: first line of "%s" not headings as expected' % inputfile)
      elif reCheckCOMPLETE.search(line) == None or reCheckERROR.search(line) != None:
        print('WARNING: deposit not marked as COMPLETE and/or marked as ERROR on line %i in "%s"' % (ln, inputfile))
        continue
      else:
        entries = extractCSVs(line, 5, ln)
        if entries:
          (timestr, currency, amount, addre, status) = entries
          date = time.strftime('%Y-%m-%d-%H-00', time.strptime(timestr, '%Y-%m-%d %H:%M:%S'))
          output.write(outputFormat % (date, currency, amount, currency, amount))

writeTransfers('depositHistory.csv', "%s, %s, -%s, %s, %s, ->poloniex\n")
writeTransfers('withdrawalHistory.csv', "%s, %s, -%s, %s, %s, poloniex->\n")

output.close()




