#!/usr/bin/python3
#
# Extract the relevant dates and aggregate from http://api.bitcoincharts.com/v1/csv/ website csv files
#
# Multiple values for the same hour-slot are averaged, weighted by the volume if available
#
# Format of 'csv' files (one entry per line after first):
# from_currency, to_currency
# date, rate
# date, rate
# ...
#
# First line of input 'csv' and 'dat' files is ignored
#
# Formats:
#   --format raw => one entry per line: unix-time, price, volume
#   --format csv => one entry per line: %Y-%m-%d-%h-%m, price
#   --format dat => one entry per line: %d-%mon-%Y, price
#   --format polo => one entry per line: %Y-%m-%d %H:%M:%S, currency-pair, ignored, ignored, price, ignored, volume, ...
#   --format krkn => one entry per line: ignored, ignored, currency-pair, %Y-%m-%d %H:%M:%S, ignored, ignored, price, volume, ...

import argparse
import os
import time
import glob
import re
import math

os.environ['TZ'] = 'UTC' # workaround for no inverse of time.gmtime(t) 

parser = argparse.ArgumentParser()
parser.add_argument("-i", "--input", help="file(s) to process", nargs="+", default="")
parser.add_argument("-o", "--output", help="file to write to", default="out.csv")
parser.add_argument("-s", "--start", help="start date (YYYY-MM-DD-HH-MM)", default="1000-01-01-00-00")
parser.add_argument("-e", "--end", help="end date (YYYY-MM-DD-HH-MM)", default="2099-12-31-23-59")
parser.add_argument("-t", "--toCurrency", help="to currency", default="TO")
parser.add_argument("-f", "--fromCurrency", help="from currency", default="FROM")
parser.add_argument("-r", "--format", help="file format", default="fromFileExt")
parser.add_argument("-c", "--computation", help="computation method from [mean|median|robust-mean]", default="mean")
parser.add_argument("-w", "--weights", help="weight mean calculation, e.g. '0.1,2,1'", default="")
args = parser.parse_args()

prices = {}
dates = []

inputs = []
for i in args.input:
  for ii in glob.glob(i):
    inputs.append(ii)

weights = args.weights.rstrip().lstrip()
if weights == '':
  weights = []
else:
  weights = re.sub('\s*,\s*', ',', weights).split(',')
  for i in range(0, len(weights)):
    weights[i] = float(weights[i])

print("Using weights " + str(weights))

class LineReader:

  def __init__(self, _format, _weight):
    if _weight == None:
      def getWeight(_w):
        if _w == 0: _w = 1.0
        return _w
    else:
      self.w = _weight
      def getWeight(_w):
        return self.w

    if _format == 'raw':
      def parse(entries):
        (unixtime, price, volume) = entries
        weight = self._getw(float(volume))
        price = float(price)
        timetup = time.gmtime(int(unixtime))
        return (timetup, price, weight)
      def check(line):
        return line != ''
    elif _format == 'csv':
      def parse(entries):
        weight = self._getw(1.0)
        (timestr, price) = entries
        timetup = time.strptime(timestr, "%Y-%m-%d-%H-%M")
        return (timetup, float(price), weight)
      def check(line):
        return line != ''
    elif _format == 'dat':
      def parse(entries):
        weight = self._getw(1.0)
        (datestr, price) = entries[0:2]
        timetup = time.strptime(datestr, '%d-%b-%Y')
        return (timetup, float(price), weight)
      def check(line):
        return line != ''
    elif _format == 'polo':
      def parse(entries):
        price = float(entries[4])
        weight = self._getw(float(entries[6]))
        timetup = time.strptime(entries[0], '%Y-%m-%d %H:%M:%S')
        return (timetup, price, weight)
      self.reCheck = re.compile(args.fromCurrency + "/" + args.toCurrency)
      def check(line):
        return line != '' and self.reCheck.search(line) != None
    elif _format == 'krkn':
      def parse(entries):
        price = float(entries[6])
        weight = self._getw(float(entries[7]))
        timestr = re.sub('\.\d+$', '', re.sub('"', '', entries[3])) # strptime can't cope with milliseconds as decimal of seconds
        timetup = time.strptime(timestr, '%Y-%m-%d %H:%M:%S')
        return (timetup, price, weight)
      currencyTranslation = {
        "BTCEUR": "XXBTZEUR",
        "BTCUSD": "XXBTZUSD",
        "BTCGBP": "XXBTZGBP",
        "ETHEUR": "XETHZEUR",
        "ETHUSD": "XETHZUSD",
        "ETHGBP": "XETHZGBP",
        "ETHBTC": "XETHXXBT",
        "ETCEUR": "XETCZEUR",
        "ETCBTC": "XETCXXBT",
        "ETCETH": "XETCXETH",
      }
      self.reCheck = re.compile(currencyTranslation[args.fromCurrency + args.toCurrency])
      def check(line):
        return line != '' and self.reCheck.search(line) != None
    else:
      sys.exit('Unknown format "%s"' % _format)

    self._parse = parse
    self._getw = getWeight
    self.check = check

  def parse(self, line):
     line = line.rstrip().lstrip()
     if line == '':
       return (0, 0, 0, 0, 0)
     success = 1
     s = re.sub('\s*,\s*', ',', line)
     entries = line.split(',')
     (timetup, price, weight) = self._parse(entries)
     (ty, tm, td, th, tn, ts, tw, tc, tt) = timetup
     timetup = (ty, tm, td, th, 0, 0, tw, tc, tt)
     timenum = time.mktime(timetup)
     timestr = time.strftime("%Y-%m-%d-%H-00", timetup)
     return (timenum, timestr, price, weight, success)

def timestr2timenum(s):
  return int(time.mktime(time.strptime(s, "%Y-%m-%d-%H-%M")))

startNum = timestr2timenum(args.start)
endNum = timestr2timenum(args.end)

#print('DEBUG: ' + args.start + ' -> ' + str(startNum))
#print('DEBUG: ' + args.end + ' -> ' + str(endNum))

for filename in inputs:
  print('Reading %s ...' % (filename))
  f = open(filename)

  frmat = args.format
  if frmat == 'fromFileExt':
    frmat = re.sub('.*\.', '', filename)

  weight = None
  if len(weights) > 0:
    weight = weights.pop(0)
  print(frmat + ', weight = ' + str(weight))

  processor = LineReader(frmat, weight)

  if frmat == 'csv' or frmat == 'dat' or frmat == 'polo' or frmat == 'krkn':
    f.readline() # ignore first line

  for line in f:
    if not processor.check(line): continue

    (timenum, timestr, price, weight, success) = processor.parse(line)

    if success and timenum >= startNum and timenum <= endNum:
      if timestr not in prices.keys():
        prices[timestr] = []
        dates.append((timenum,timestr))

      prices[timestr].append((float(price), float(weight)))


def addHours(ut, h):
  (ty, tm, td, th, tn, ts, tw, tc, tt) = time.gmtime(ut)
  return time.mktime((ty, tm, td, th + h, tn, ts, tw, tc, tt))


class ConvPrinter:
  def __init__(self, _tinit, _filename, _function):
    self.f = _filename
    self.lastt = _tinit
    self.lastv = 0
    self.tstep = 3600 # hour in seconds
    if _function == 'median':
      self.range = 5
      self.delay = 2
      self.vBuffer = [0,0,0]
      self.dBuffer = []
      def post_(_d, _v):
        self.vBuffer.append(_v)
        if len(self.vBuffer) > self.range:
          self.vBuffer.pop(0)

        self.dBuffer.append(_d)
        if len(self.dBuffer) > self.delay:
          i = self.delay 
          v = self.vBuffer[i]
          # calculate median
          l = self.vBuffer.copy()
          l.sort()
          median = l[i]
          deviation = v - median
          threshold = 0.08
          if abs(deviation) > threshold * median:
            sign = math.copysign(1, deviation)
            v = median + sign * threshold * median
          d = self.dBuffer.pop(0)
          self._print(d, v)
      def flush_():
        d = self.dBuffer(len(self.dBuffer) - 1)
        v = self.vBuffer(len(self.vBuffer) - 1)
        for i in range(0, self.delay):
          self._post(d, v)

    else:
      def post_(_d, _v):
        self._print(_d, _v)
      def flush_():
        return None

    self._post = post_
    self.flush = flush_

  def _print(self, _d, _v):
    print("%s, %f" % (_d, _v), file=self.f)

  def post(self, _t, _v):
    if _t[0] - self.lastt[0] > self.tstep:
      ut = addHours(self.lastt[0], 1)
      while ut < _t[0]:
        d = time.strftime("%Y-%m-%d-%H-00", time.gmtime(ut))
        self._post(d, self.lastv)
        ut = addHours(ut, 1)

    d = t[1]
    self._post(d, _v)
    self.lastt = _t
    self.lastv = _v


class ComputationEngine:
  def __init__(self, _function):
    if _function == 'mean':
      self.p_sum = 0
      self.w_sum = 0
      def add(_p, _w):
        self.p_sum += _p * _w
        self.w_sum += _w
      def compute():
        v = self.p_sum / self.w_sum
        # reset
        self.p_sum = 0
        self.w_sum = 0
        return v

    elif _function == 'median':
      self.ps = []
      def add(_p, _w):
        self.ps.append(_p)
      def compute():
        self.ps.sort()
        n = len(self.ps)
        n_ = math.floor(n)
        if n == n_:
          v = self.ps[n]
        else:
          v = (self.ps[n_] + self.ps[n_ + 1]) / 2
        # reset
        self.ps = []
        return v

    else:
      sys.exit('Unknown compute method "%s"' % _function)

    self.add = add
    self.compute = compute

f = open(args.output, mode='w')
print('Writing to %s ...' % (args.output))
print(args.fromCurrency + ", " + args.toCurrency, file=f)

dates.sort(key=lambda t : t[0])

if args.computation == 'mean':
  preComputation = 'mean'
  postComputation = None
elif args.computation == 'median':
  preComputation = 'median'
  postComputation = None
elif args.computation == 'robust-mean':
  preComputation = 'mean'
  postComputation = 'median'
else:
  preComputation = None
  postComputation = None

convFile = ConvPrinter(dates[0], f, postComputation)
engine = ComputationEngine(preComputation)

for t in dates:
  for (p, w) in prices[t[1]]:
    engine.add(p, w)

  v = engine.compute()
  convFile.post(t, v)

convFile.flush()




