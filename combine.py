#!/usr/bin/python3
#
# Combine two 'conversion' files CUR1->CUR2 and CUR2->CUR3
# and generate a new 'conversion file CUR1->CUR3
#
# File format, one entry per line:
# from_currency, to_currency
# date, rate
# date, rate
# ...

import sys
import argparse
import re

def extractCSVs(s):
  return re.sub('\s*,\s*', ',', line.rstrip()).split(',')

parser = argparse.ArgumentParser()
ordinals = [(1, 'first'), (2, 'second'), (3, 'third'), (4, 'fourth'), (5, 'fifth')]
for (n, o) in ordinals:
  parser.add_argument('-' + str(n), '--' + o, help=(o + ' file in currency chain'), default='')
parser.add_argument('-o', '--output', help='output filename', default='out.csv')

args = parser.parse_args()

data = {}
dates = []
currencies = []
fileCount = 0

for (n, o) in ordinals:
  filename = args.__dict__[o]
  if filename != '':
    print('Reading %s ...' % (filename))
    fileCount += 1
    f = open(filename)
    line = f.readline()
    (fcurr, tcurr) = extractCSVs(line)
    if n == 1:
      currencies.append(fcurr)
    elif fcurr != currencies[n - 1]:
      sys.exit('Currency mismatch in ' + o + ' file! ' + currencies[n - 1] + ' <> ' + fcurr)

    currencies.append(tcurr)

    for line in f:
      (date, rate) = extractCSVs(line)
      if date not in data.keys():
        data[date] = [1, 0]
        dates.append(date)
      data[date][0] *= float(rate)
      data[date][1] += 1

print('Read %d files' % (fileCount))

dates.sort()

f = open(args.output, mode='w')
print('Writing to %s ...' % (args.output))

print('%s, %s' % (currencies[0], currencies[len(currencies)-1]), file=f)
for d in dates:
  if data[d][1] == fileCount:
    print('%s, %f' % (d, data[d][0]), file=f)
  #else:
  #  print('INFO: skipping %s - insufficient chain :: %f' % (d, data[d][0]))




