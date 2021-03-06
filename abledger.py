#!/usr/bin/python3
#
# Read csv files and calculate gains or losses under Section 104 aggregation, 
# the "bed and breakfast" rule, and disregarding of accounts in debt
#
# 'ledger' files, one entry per line, negative signifies 'from-currency':
# date, currency, value, currency, value, transfer-info
#
# 'convertion' files, one entry per line:
# from_currency, to_currency
# date, rate
# date, rate
# ...
#
# date is %Y-%m-%d-%H-%M
# transfer-info is blank or account1->acount2
#
# 'ledger' files can also be csv files from poloniex, bitstamp, kraken, etc
#
# 'account' file(s) used for initialization, one entry per line:
# account*, currency, amount, baseCurrency, value
#
# *<account> can be blank, but if not, should match the filename of the input
# file it corresponds to
#

import sys
import os
import glob
import argparse
import re
import time
import math
import csv

os.environ['TZ'] = 'UTC' # workaround for no inverse of time.gmtime(t) 
TOLERANCE = 1e-6
FLOAT_ZERO = 1e-8

parser = argparse.ArgumentParser()

parser.add_argument("-i", "--input", help="csv file(s) to read", default="ledgers/*.csv")
parser.add_argument("-b", "--base", help="base currency", default="GBP")
parser.add_argument("-c", "--conversion", help="translation table(s) for currency conversions", default="conversions/*.csv")
parser.add_argument("-s", "--start", help="start date (YYYY-MM-DD-HH-MM)", default="1000-01-01-00-00")
parser.add_argument("-e", "--end", help="end date (YYYY-MM-DD-HH-MM)", default="2099-12-31-23-59")
parser.add_argument("-a", "--accounts", help="pre-ledger account states", default=".accounts")

# TODO: base currency check / switching
# TODO: allow "unchargeable" flag for transactions that were for personal use (e.g. pizza purchase)
# TODO: improve fee (zero value tx) handling

args = parser.parse_args()
print(args) # DEBUG

inputs = glob.glob(args.input)

if len(inputs) == 0:
  sys.exit('need input csv(s)')

conversionFiles = glob.glob(args.conversion)
baseCurrency = args.base
accountsFiles = glob.glob(args.accounts)

monthLengths = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

def numberDaysBetween(_start, _end):
  global monthLengths
  # TODO: use package with leap-year support
  (year1, month1, day1) = re.sub('[/ ;:]', '-', _start).split('-')[:3]
  (year2, month2, day2) = re.sub('[/ ;:]', '-', _end).split('-')[:3]
  if year1 > year2:
    print('WARNING: numberDaysBetween - bad year order: start = %s; end = %s' % (_start, _end))
    return -numberDaysBetween(_end, _start)
  elif year1 < year2:
    iend = year1 + '-12-31'
    istart = year2 + '-01-01'
    return numberDaysBetween(_start, iend) + (365 * (int(year2) - int(year1) - 1)) + numberDaysBetween(istart, _end)
  else:
    day1 = int(day1)
    day2 = int(day2)
    month1 = int(month1) - 1
    month2 = int(month2) - 1
    # leap year hack
    if month1 == 1 and day1 == 29: day1 = 28
    if month2 == 1 and day2 == 29: day2 = 28
    # calculate diff
    if month1 >= 12 or month2 >= 12:
      exit('ERROR: numberDaysBetween - bad month(s): start = %s; end = %s' % (_start, _end))
    elif month1 > month2:
      exit('WARNING: numberDaysBetween - bad month order: start = %s; end = %s' % (_start, _end))
      #return -numberDaysBetween(_end, _start)
    elif day1 > monthLengths[month1] or day2 > monthLengths[month2]:
      exit('ERROR: numberDaysBetween - bad day(s): start = %s; end = %s' % (_start, _end))
    elif month1 < month2:
      return (monthLengths[month1] - day1) + sum(monthLengths[month1 + 1:month2]) + (day2)
    elif day1 > day2:
      exit('WARNING: numberDaysBetween - bad day order: start = %s; end = %s' % (_start, _end))
      #return -numberDaysBetween(_end, _start)
    else:
      return day2 - day1


def extractCSVs(_s, _n, _i):
  # TODO: pass error up instead of passing line number down
  line = _s.rstrip().lstrip()
  if line == '':
    return []
  for e in csv.reader([line], quotechar='"', delimiter=',', quoting=csv.QUOTE_ALL, skipinitialspace=True):
    vs = e
  if len(vs) != _n:
    exit('ERROR: Incorrect number of entries on line %d (expecting %d, got %d)' % (_i, _n, len(vs)))
  return vs


class FileWriter:
  def __init__(self, _filename):
    self.f = open('./output/' + _filename, 'w')
    formatdef = [('date', '%s'), ('id', '%s'), ('account', '%s'), ('base', '%s'), ('value', '%f'), ('currency', '%s'), ('amount', '%f'), ('chargeable', '%f'), ('profit', '%f')]
    self.categories, formats = zip(*formatdef)
    self.f.write(', '.join(map(str.title, self.categories)) + ", Base Balance, Currency Balance, Aggregated Rate, Chargeable Total, Profit Total\n")
    self.format = ', '.join(formats) + ",=sum(e$2:e%d),=sum(g$2:g%d),=max(0; j%d/k%d),=sum(h$2:h%d),=sum(i$2:i%d)\n"
    #self.f.write(', '.join(map(str.title, self.categories)) +"\n")
    #self.format = ', '.join(formats) + "\n"
    self.ln = 1

  def addline(self, _data):
    self.ln += 1
    data = [_data[k] for k in self.categories]
    data += [self.ln, self.ln, self.ln, self.ln, self.ln, self.ln]
    self.f.write(self.format % tuple(data))

    #print(self.format % tuple(data)) 


class Account:
  def __init__(self, _name, _curr):
    self.name = _name
    self.currency = _curr # name of foreign currency
    self.txs = {} # all txs by date key
    self.ledger = [] # ordered list of transactions
    self.queue = [] # "bed and breakfast" queue 
    self.balance = 0.0 # ongoing balance in foreign currency
    self.profit = 0.0 # total profit in base currency
    self.poolBalance = 0.0 # in foreign currency '_name'
    self.poolCost = 0.0 # in base currency
    self.chargeable = 0.0 # gains in base (on disposals while account above zero)
    self.warning = False
    self.output = FileWriter(_name + ".csv")

  def __str__(self):
    return '%s {balance: %f,   \tcost: %f, \tchargeable: %f}' % (self.name, self.totalBalance(), self.poolCost, self.chargeable)

  def poolRate(self):
    if abs(self.poolBalance) < FLOAT_ZERO:
      return 0.0
    else:
      return max(0.0, self.poolCost / self.poolBalance)

  def totalBetween(self, attrName, startDate, endDate):
    #print("DEBUG: %s.%s between %s and %s" % (attrName, self.name, startDate, endDate))
    v = 0.0
    for tx in self.ledger:
      if tx.date < startDate: continue
      elif tx.date > endDate: continue
      #elif tx.date > endDate: break
      v += getattr(tx, attrName)
    return v
   
  def profitBetween(self, startDate, endDate):
    return self.totalBetween('profit', startDate, endDate)

  def chargeableBetween(self, startDate, endDate):
    return self.totalBetween('chargeable', startDate, endDate)

  def balanceAt(self, endDate):
    return self.totalBetween('amount', self.earliestDate, endDate)
  
  def costAt(self, endDate):
    return self.totalBetween('value', self.earliestDate, endDate)

  def totalBalance(self):
    return self.totalBetween('amount', self.earliestDate, self.latestDate)

  def totalCost(self):
    return self.totalBetween('value', self.earliestDate, self.latestDate)

  def proceedsBetween(self, startDate, endDate):
    n = 0.0
    p = 0.0
    for tx in self.ledger:
      if tx.date < startDate: continue
      elif tx.date > endDate: continue
      #elif tx.date > endDate: break
      elif abs(tx.chargeable) > FLOAT_ZERO:
        p += -tx.value
        n += 1
    return (p, n)

  def clearQueueToDate(self, _d, _limit):
    while len(self.queue) > 0 and numberDaysBetween(self.queue[0].date, _d) > _limit:
      self.addTXtoPool(self.queue.pop(0))

  def clearQueue(self):
    for tx in self.queue:
      self.addTXtoPool(tx)
    self.queue.clear()

  def addTXtoPool(self, _tx):
    (a, v) = _tx.useUp()

    # a >= 0: deposit - not chargeable
    # self.poolBalance <= 0: debt account - not chargeable
    g = 0.0
    c = 0.0
    b = 0.0
    p = 0.0
    #print("DEBUG: adding TX{%f %s, %f %s) to Pool{%f %s, %f %s}" % (a, self.name, v, baseCurrency, self.poolBalance, self.name, self.poolCost, baseCurrency))

    if a < -FLOAT_ZERO and self.poolBalance > FLOAT_ZERO:
      # disposal from an account in credit
      c = min(self.poolBalance, -a)
      # cost basis of this amount based on aggregated acquisition
      b = c * self.poolRate()
      # gain
      g = (v * c / a) - b
      p = g
      self.poolCost = (self.poolBalance + a) / self.poolBalance * self.poolCost
    elif a > FLOAT_ZERO and self.poolBalance < -FLOAT_ZERO:
      # deposit on account in debt
      c = min(-self.poolBalance, a)
      b = c * self.poolRate()
      p = (v * c / a) - b
      self.poolCost = (self.poolBalance + a) / self.poolBalance * self.poolCost
    else:
      self.poolCost += v

    _tx.addProfitAndChargeable(p, g)
    self.poolBalance += a
    #print("%s, %s, %s, %s, %f, %f, %f, %f, %f, %f" % (_tx.id, _tx.date, ('buy', 'sell')[_tx.amount < 0.0], "pool", a, v, p, g, self.poolBalance, self.poolCost))

    # warn if in debt
    if self.poolBalance < -1e-6 and not self.warning and self.name != baseCurrency and abs(a) > TOLERANCE:
      self.warning = True
      print('WARNING: disposal of unowned assets in "%s" account: poolBalance = %f, disposal = %f, date = %s' % (self.name, self.poolBalance, a, _tx.date))

  def processTX(self, _tx):
    self.ledger.append(_tx)
    if _tx.amount < -FLOAT_ZERO:
      # set chargeable status
      # only the balance on the account counts as a chargeable disposal
      #if self.balance < -FLOAT_ZERO:
      #  _tx.chargeableMultiplier = 0.0
      #elif self.balance + _tx.amount < -FLOAT_ZERO:
      #  _tx.chargeableMultiplier = max(0, self.balance / abs(_tx.amount))
      #else:
      _tx.chargeableMultiplier = 1.0
      self.queue.append(_tx)
    else:
      # deposits not chargeable
      _tx.chargeableMultiplier = 0.0

      # calculate profit; first in, last out
      while len(self.queue) > 0 and self.queue[len(self.queue) - 1]._unusedAmount + _tx._unusedAmount > FLOAT_ZERO:
        qtx = self.queue.pop()
        (a, v) = qtx.useUp()
        p = _tx.adjust(a) - v
        g = p * qtx.chargeableMultiplier
        qtx.addProfitAndChargeable(p, g)
        
      if len(self.queue) > 0:
        qtx = self.queue[len(self.queue) - 1]
        (a, v) = _tx.useUp()
        p = qtx.adjust(a) - v
        g = p * qtx.chargeableMultiplier
        qtx.addProfitAndChargeable(p, g)

      else:
        self.addTXtoPool(_tx)

    self.balance += _tx.amount


  def addTX(self, _tx):
    if _tx.date in self.txs:
      self.txs[_tx.date].append(_tx)
    else:
      self.txs[_tx.date] = [_tx]

  def process(self):
    dates = list(self.txs.keys())
    dates.sort()
    self.earliestDate = dates[0]
    self.latestDate = dates[len(dates) - 1]
    for d in dates:
      # match sells with buy within 30 days if available, otherwise section 104 pool
      self.clearQueueToDate(d, 30)

      # match sells with buys on same day if available, so add today's sells first
      day_buys = []
      for tx in self.txs[d]:
        if tx.amount < 0.0:
          self.processTX(tx)
        else:
          day_buys.append(tx)

      for tx in day_buys:
        self.processTX(tx)

    self.clearQueue()

    for tx in self.ledger:
      # record gains
      self.profit += tx.profit
      self.chargeable += tx.chargeable

      # write to ledger file
      self.output.addline({
        'profit': tx.profit,
        'chargeable': tx.chargeable, 
        'date': tx.date, 
        'value': tx.value, 
        'amount': tx.amount, 
        'base': baseCurrency, 
        'account': self.name,
        'currency': self.currency, 
        'basebalance': self.poolCost, 
        'currbalance': self.poolBalance, 
        'id': tx.id
      })

  def __str__(self):
    txss = "..."
    #for d in self.txs:
    #  txss += d + ":\n"
    #  for tx in self.txs[d]:
    #    txss += str(tx) + "\n"
    txls = ""
    for tx in self.ledger:
      txls += str(tx) + "\n"
    return "%s\ntxs:\n%sledger:\n%s" % (self.name, txss, txls)


class TX:
  def __init__(self, _a, _v, _d, _id):
    #print("DEBUG TX.__init__(%f, %f, %s)" % (_a, _v, _d))

    self.profit = 0.0 # in base
    self.chargeable = 0.0 # in base
    self.amount = _a # in foreign currency (negative is disposal)
    self.value = math.copysign(_v, _a) # in GBP (base should be same as amount)
    self._unusedAmount = self.amount
    self._unusedValue = self.value
    self.date = _d
    self.id = _id
    self.chargeableMultiplier = float(_a < 0.0) # depends also on account balance when tx is executed
    if abs(_a) > FLOAT_ZERO:
      self.rate = _v / _a
    else:
      self.rate = 0.0

  def __str__(self):
    datestr = re.sub('-', '/', self.date[:10]) + ' ' + re.sub('-', ':', self.date[11:16])
    return 'amount = %f; value = %f; rate = %f; unused{amount = %f; value = %f}; profit = %f; chargeable = %f; (%s)' % (self.amount, self.value, self.rate, self._unusedAmount, self._unusedValue, self.profit, self.chargeable, datestr)

  def addProfitAndChargeable(self, _p, _c):
    self.profit += _p
    self.chargeable += _c
    #if _c > _p + TOLERANCE: print("ARGH: %s :: profit: %f -> %f; chargeable: %f -> %f" % (self.date, self.profit - _p, self.profit, self.chargeable - _c, self.chargeable))

  def adjust(self, _a):
    if abs(_a) <= FLOAT_ZERO:
      return 0.0
    if self._unusedAmount * _a > 0.0:
      exit("ERROR: TX.adjust: attempt to add further to a tx (tx amount = %f; adjust amount = %f)" % (self._unusedAmount, _a))
    if abs(_a) - abs(self._unusedAmount) > FLOAT_ZERO:
      exit("ERROR: TX.adjust: attempt to adjust by more than available (tx amount = %f; adjust amount = %f)" % (self._unusedAmount, _a))
    self._unusedAmount += _a
    v = self._unusedValue
    self._unusedValue += _a * self.rate
    return self._unusedValue - v # value of adjustment, i.e. new = old + return_value

  def useUp(self):
    a = self._unusedAmount
    v = self._unusedValue
    self._unusedAmount = 0.0
    self._unusedValue = 0.0
    return (a, v)

def createTXid(acc1, acc2, val, date, salt):
  s = str(abs(hash((acc1, acc2, val, date, salt))))
  h = ""
  for i in range(0, math.floor(len(s) / 2)):
    n = int(s[i:i + 2]) + 45
    if n > 90: n += 3
    if n > 122: h += 'X'
    else: h += chr(n)
  return h

# read pre-ledger state and initialize
accounts = {baseCurrency: Account(baseCurrency, baseCurrency)}
for filename in accountsFiles:
  print('Reading bootstrap account data from %s ...' % (filename))
  f = open(filename)
  i = 0
  for line in f:
    i += 1
    accountInfo = extractCSVs(line, 5, i)
    if len(accountInfo) > 0:
      if accountInfo[3] == baseCurrency:
        name = accountInfo[0]
        currency = accountInfo[1]
        amount = float(accountInfo[2])
        value = float(accountInfo[4])
        # create account
        if currency not in accounts:
          accounts[currency] = Account(name, currency)
        # add to ledger(s)
        id_ = createTXid(currency, baseCurrency, value, args.start, filename)
        accounts[currency].addTX(TX(amount, value, args.start, id_))
        if currency != baseCurrency:
          accounts[baseCurrency].addTX(TX(-value, -value, args.start, id_))
        # TODO: custom accounts init date
      else:
        exit('ERROR: Invalid base currency for account on line %d' % i)

class CurrencyConverter:
  def __init__(self):
    self.conversions = {}
    self.fromCurrencies = []
    self.toCurrencies = []

  def _formatDate(self, date):
    return date[:-2] + "00" # ignore minutes

  def currencies(self):
    return self.fromCurrencies

  def canConvertOn(self, date, fromCurrency, toCurrency):
    date = self._formatDate(date)
    symb = fromCurrency + toCurrency
    return symb in self.conversions and date in self.conversions[symb]

  def convert(self, date, fromCurrency, toCurrency, fromValue):
    date = self._formatDate(date)
    symb = fromCurrency + toCurrency
    return fromValue * self.conversions[symb][date]

  def loadPairData(self, filename):
    print('Reading currency conversion data from %s ... ' % (filename), end='')
    f = open(filename)
    line = f.readline()
    entries = extractCSVs(line, 2, 1)
    print('(' + ' -> '.join(entries) + ')')
    currFrom = entries[0]
    currTo = entries[1]
    csym = currFrom + currTo
    self.conversions[csym] = {}
    self.fromCurrencies.append(currFrom)
    self.toCurrencies.append(currTo)
    #rsym = currTo + currFrom
    #ronversions[rsym] = {}
    i = 1

    lastt = 0

    for line in f:
      i += 1
      entries = extractCSVs(line, 2, i)
      date = self._formatDate(entries[0])
      rate = float(entries[1])
      self.conversions[csym][date] = rate;
      #ronversions[rsym][date] = 1.0 / rate;

currencyPairs = CurrencyConverter()

for filename in conversionFiles:
  currencyPairs.loadPairData(filename)

class InputTX:
  def __init__(self, _d, _c1, _v1, _c2, _v2):
    self.date = _d
    self.curr1 = _c1
    self.account1 = _c1
    self.amount1 = _v1
    self.curr2 = _c2
    self.account2 = _c2
    self.amount2 = _v2
    self.isTransfer = False

  def flagAsTransfer(self):
    self.isTransfer = True

  def __str__(self):
    return "<%s> %f %s -> %f %s %s%s %s" % (self.account1, self.amount1, self.curr1, self.amount2, self.curr2, ('<' + self.account2 + '>', '')[self.account2 == self.account1], ('', '*')[self.isTransfer], self.date)

class FileReader:
  def __init__(self, _firstline):
    firstline = _firstline.rstrip()

    if firstline == "Date, From-Currency, Amount, To-Currency, Value":
      # basic
      def parseline(line, ln):
        entries = extractCSVs(line, 5, ln)
        if len(entries) == 0:
          return None # TODO: deal with this return value
        date = time.strftime("%Y-%m-%d-%H-%M", time.strptime(entries[0], "%d/%m/%Y %H:%M:%S"))
        return InputTX(date, entries[1], float(entries[2]), entries[3], float(entries[4]))

    elif firstline == "Date,Market,Category,Type,Price,Amount,Total,Fee,Order Number,Base Total Less Fee,Quote Total Less Fee":
      # poloniex
      def parseline(line, ln):
        entries = extractCSVs(line, 11, ln)
        if len(entries) == 0:
          return None
        isMargin = False
        (timestr, market, category, type_, price, amount, total, fee, num, base, quote) = entries
        date = time.strftime("%Y-%m-%d-%H-%M", time.strptime(timestr, "%Y-%m-%d %H:%M:%S"))
        (cur1, cur2) = market.split('/')
        val1 = float(quote)
        val2 = float(base)

        if category == 'Margin trade':
          isMargin = True
        elif category == 'Settlement':
          isMargin = True
          val1 = 0 # paying off lending fees
        elif category != 'Exchange':
          exit('ERROR: Unknown trade category "%s" on line %i' % (category, _i))

        if type_ == "Buy": 
          if val1 < 0 or val2 > 0:
            exit('ERROR: Inconsistent %s on line %i: %f %s <> %f %s' % (type_, _i, val1, cur1, val2, cur2))
        elif type_ == "Sell":
          if val1 > 0 or val2 < 0:
            exit('ERROR: Inconsistent %s on line %i: %f %s <> %f %s' % (type_, _i, val1, cur1, val2, cur2))
        else:
          exit('ERROR: Unknown trade type "%s" on line %i' % (type_, _i))

        tx = InputTX(date, cur1, val1, cur2, val2)

        if isMargin:
          tx.account1 += 'margin'
          tx.account2 += 'margin'

        return tx

    elif firstline == '"txid","ordertxid","pair","time","type","ordertype","price","cost","fee","vol","margin","misc","ledgers"':
      # kraken
      self.currencyTranslation = {
        "XXBTZEUR": ("BTC", "EUR"),
        "XXBTZUSD": ("BTC", "USD"),
        "XXBTZGBP": ("BTC", "GBP"),
        "XETHZEUR": ("ETH", "EUR"),
        "XETHZUSD": ("ETH", "USD"),
        "XETHZGBP": ("ETH", "GBP"),
        "XETHXXBT": ("ETH", "BTC"),
        "XETCZEUR": ("ETC", "EUR"),
        "XETCXXBT": ("ETC", "BTC"),
        "XETCXETH": ("ETC", "ETH")
      }

      def parseline(line, ln):
        entries = extractCSVs(line, 13, ln)
        if len(entries) == 0:
          return None
        (txid, txid2, curstr, timestr, type_, category, price, cost, fee, vol, margin, misc, txid3) = entries
        timestr = re.sub('\.\d+$','',timestr) # strptime can't cope with milliseconds as decimal of seconds
        date = time.strftime("%Y-%m-%d-%H-%M", time.strptime(timestr, "%Y-%m-%d %H:%M:%S"))

        #if float(margin) != 0: exit("UNEXPECTED KRAKEN MARGIN USAGE (on line %d)!" % ln)
        if float(fee)/float(cost) > 0.005 and float(fee) > 0.00001: exit("UNEXPECTED KRAKEN FEE SCHEDULE (%f on line %d)!" % (float(fee)/float(cost), ln))

        val1 = float(vol)
        val2 = float(cost) - float(fee) # TODO: work out how Kraken reports fee curency

        if type_ == "sell": val1 *= -1
        elif type_ == "buy": val2 *= -1
        else: exit("UNEXPECTED KRAKEN TYPE APPEARED ('%s' on line %d)!" % (type_, ln))

        if curstr in self.currencyTranslation:
          (cur1, cur2) = self.currencyTranslation[curstr]
        else:
          exit("ERROR: don't know what currencies are involved in the Kraken pair '%s' on line %d" % (curstr,  ln))

        return InputTX(date, cur1, val1, cur2, val2)
    
    elif firstline == "Type,Datetime,Account,Amount,Value,Rate,Fee,Sub Type":
      # bitstamp
      self.validCategories = ["Market", "Deposit", "Withdrawal"]
      def parseline(line, ln):
        entries = extractCSVs(line, 8, ln)
        if len(entries) == 0:
          return None
        (category, timestr, account, amount, value, rate, fee, type_) = entries
        if category not in self.validCategories:
          return None
        
        date = time.strftime("%Y-%m-%d-%H-%M", time.strptime(timestr, "%b. %d, %Y, %I:%M %p")) # Sep. 13, 2014, 08:25 AM
        (amount, cur1) = amount.split(" ")
        val1 = float(amount)

        if category == "Market":
          (value, cur2) = value.split(" ")
          val2 = float(value)
          if type_ == "Sell": val1 *= -1
          elif type_ == "Buy": val2 *= -1
          else: exit("UNEXPECTED BITSTAMP TYPE APPEARED ('%s' on line %d)!" % (type_, ln))

          if fee != "":
            (fee, fcur) = fee.split(" ")
            if fcur == cur1: val1 -= float(fee)
            elif fcur == cur2: val2 -= float(fee)
            else: exit("UNEXPECTED BITSTAMP FEE CURRENCY ('%s' on line %d)!" % (fcur, ln))

          tx = InputTX(date, cur1, val1, cur2, val2)

        elif category == "Deposit":
          val2 = -val1
          cur2 = cur1
          tx = InputTX(date, cur1, val1, cur2, val2)
 
          tx.account1 = "bitstamp" + cur1
          tx.flagAsTransfer()
        
        elif category == "Withdrawal":
          val1 = -val1
          val2 = -val1
          cur2 = cur1
          tx = InputTX(date, cur1, val1, cur2, val2)
 
          tx.account1 = "bitstamp" + cur1
          tx.flagAsTransfer()

        else:
          exit("ERROR: unexpected category '%s' slipped through the switch :-(" % category)

        return tx

    elif firstline == "Date, Base Currency, Value, Trade Currency, Amount, Transfer Info":
      # raw
      def parseline(line, ln):
        entries = extractCSVs(line, 6, ln)
        if len(entries) == 0:
          return None
        (timestr, cur1, val1, cur2, val2, transferInfo) = entries
        date = time.strftime("%Y-%m-%d-%H-%M", time.strptime(timestr, "%Y-%m-%d-%H-%M"))
        if val1 == "" and val2 == "": exit("ERROR: no values for transaction on %s (line %d)" % (date, ln))
        if val1: val1 = float(val1)
        if val2: val2 = float(val2)

        if val1 == "":
          if currencyPairs.canConvertOn(date, cur2, cur1): val1 = -currencyPairs.convert(date, cur2, cur1, val2)
          else: exit("ERROR: failed to determine value of %f %s in %s on %s (line %d)" % (val2, cur2, cur1, date, ln))

        if val2 == "":
          if currencyPairs.canConvertOn(date, cur1, cur2): val2 = -currencyPairs.convert(date, cur1, cur2, val1)
          else: exit("ERROR: failed to determine value of %f %s in %s on %s (line %d)" % (val1, cur1, cur2, date, ln))

        tx = InputTX(date, cur1, val1, cur2, val2)
        if transferInfo != "": 
          if val1 != -val2 or cur1 != cur2:
            exit("ERROR: Invalid account transfer set for %s (line %d): '%s': %f %s -> %f %s" % (date, ln, transferInfo, val1, cur1, val2, cur2))
          tx.account1 = re.sub('->[^-]*$', '', transferInfo) + tx.curr1
          tx.account2 = re.sub('^[^-]*->', '', transferInfo) + tx.curr2
          tx.flagAsTransfer()

        return tx

    elif firstline == 'Reference,Date,Type,Description,Amount,Currency,Status,"Received Date","Transfer Reference"':
      # currencyfair transfers
      def parseline(line, ln):
        entries = extractCSVs(line, 9, ln)
        if len(entries) == 0:
          return None
        (ref, instructionDate, type_, desc, amount, currency, status, actionDate, reference) = entries
        if status != "confirmed":
          return None
        date = time.strftime("%Y-%m-%d-%H-%M", time.strptime(actionDate, "%d-%b-%Y %H:%M"))
        amount = re.sub(',', '', amount)
        cur2 = currency
        val2 = float(amount)
        if type_ == "Deposit In" or type_ == "Transfer Out":
          cur1 = currency
          val1 = -float(amount)
          tx = InputTX(date, cur1, val1, cur2, val2)
          tx.account2 = "currencyfair" + cur1
          tx.flagAsTransfer()
        elif type_ == "Referral Success":
          cur1 = baseCurrency
          val1 = 0.0
          tx = InputTX(date, cur1, val1, cur2, val2)
        else:
          exit("ERROR: unexpected type '%s' encountered in line %d" % (type_, ln))

        return tx

    elif firstline == 'Reference,Date,Exchange Type,Order Rate,Amount Placed,Status,Amount Purchased':
      # currencyfair trades
      def parseline(line, ln):
        entries = extractCSVs(line, 7, ln)
        if len(entries) == 0:
          return None
        (ref, timestr, currencies, rate, given, status, received) = entries
        if status != "matched":
          #print("DEBUG: ignoring cancelled CurrencyFair exchange '%s'" % line)
          return None
        date = time.strftime("%Y-%m-%d-%H-%M", time.strptime(timestr, "%d-%b-%Y %H:%M"))
        (val1, cur1) = given.split(" ")
        (val2, cur2) = received.split(" ")
        val1 = -float(re.sub(',', '', val1))
        val2 = float(re.sub(',', '', val2))

        return InputTX(date, cur1, val1, cur2, val2)

    elif firstline == '﻿"Closed Date","Opened Date","Market","Type","Bid/Ask","Units Filled","Units Total","Actual Rate","Cost / Proceeds"':
      # bittrex trades
      def parseline(line, ln):
        entries = extractCSVs(line, 9, ln)
        if len(entries) == 0:
          return None
        (timestr, opentimestr, currencies, type_, quoterate, amount, ordertotal, rate, cost) = entries
        date = time.strftime("%Y-%m-%d-%H-%M", time.strptime(timestr, "%m/%d/%Y %I:%M:%S %p")) # 09/29/2016 02:16:36 AM
        (cur1, cur2) = currencies.split("-")
        val1 = float(cost)
        val2 = float(amount)

        return InputTX(date, cur1, val1, cur2, val2)

    elif firstline == '#,Pair,Amount,Price,Date':
      # bitfinex trades
      def parseline(line, ln):
        entries = extractCSVs(line, 5, ln)
        if len(entries) == 0:
          return None
        (id_, currencies, amount, rate, timestr) = entries
        date = time.strftime("%Y-%m-%d-%H-%M", time.strptime(timestr, "%Y-%m-%d %H:%M:%S")) # 2016-01-08 20:02:45
        cur1 = currencies[:3]
        cur2 = currencies[-3:]
        val1 = float(amount)
        val2 = -float(amount) * float(rate)

        return InputTX(date, cur1, val1, cur2, val2)

    elif firstline == 'Currency,Description,Amount,Balance,Date':
      # bitfinex ledger
      def parseline(line, ln):
        entries = extractCSVs(line, 5, ln)
        if len(entries) == 0:
          return None
        (currency, desc, amount, balance, timestr) = entries
        date = time.strftime("%Y-%m-%d-%H-%M", time.strptime(timestr, "%Y-%m-%d %H:%M:%S")) # 2016-01-08 20:02:45
        cur1 = 'GBP'
        cur2 = currency
        val1 = 0.0
        val2 = float(amount)

        if re.match('^Transfer', desc):
          tx = None
        elif re.search('Deposit', desc) != None or re.search('Withdrawal', desc) != None:
          cur1 = cur2
          val1 = -val2
          tx = InputTX(date, cur1, val1, cur2, val2)
          tx.account2 = 'bitfinex' + cur2
          tx.flagAsTransfer()
        elif (re.match('^Extraordinary', desc) != None or 
              re.match('^Trading fee', desc) != None or 
              re.match('^Settlement', desc) != None or 
              re.match('^Adjustment', desc) != None or 
              re.match('^Position', desc) != None or 
              re.match('^Exchange', desc) != None or
              re.match('^BFX ', desc) != None):
          tx = InputTX(date, cur1, val1, cur2, val2)
        else:
          exit('ERROR: unknown ledger description \'%s\' reading bitfinex report file on line %d' % (desc, ln))

        # check
        if re.match('^Exchange', desc):
          m = re.match('^Exchange (\S+) (\w{3}) for (\w{3}) @ (\S+) on', desc)
          if m == None:
            exit("ERROR: expecting '%s' but got '%s' on line %d" % ('^Exchange (\S+) (\w{3}) for (\w{3}) @ (\S+) on', desc, ln))
          (a1, c1, c2, rate) = m.groups()
          if c1 == currency:
            if abs(abs(float(a1)) - abs(val2)) > TOLERANCE:
              exit("ERROR: ledger amount %f doesn't match amount %f in exchange entry description '%s' on line %d" % (val2, a1, desc, ln))
            cur1 = c2
            val1 = -val2 * float(rate)
          elif c2 == currency:
            cur1 = c1
            val1 = -math.copysign(float(a1), val2)
            val2check = -val1 * float(rate)
            if abs(val2 - val2check) > TOLERANCE:
              exit("ERROR: ledger amount %f doesn't match calculated amount %f in exchange entry description '%s' on line %d" % (val2, val2check, desc, ln))
          else:
            exit("ERROR: couldn't find ledger currency '%s' in exchange entry description '%s' -> '%s' & '%s' on line %d" %s (currency, desc, c1, c2, ln))

        return tx

    elif firstline == 'Pair,Type,Price,Amount,Fee Rate,maker/taker,Total paid,Amount received,Date and time':
      # gatecoin
      def parseline(line, ln):
        entries = extractCSVs(line, 9, ln)
        if len(entries) == 0:
          return None
        (currencies, type_, rate, offer, feerate, category, paid, received, timestr) = entries
        date = time.strftime("%Y-%m-%d-%H-%M", time.strptime(timestr, "%Y-%m-%d %H:%M:%S")) # 2016-05-07 00:39:42
        curcheck1 = currencies[:3]
        curcheck2 = currencies[-3:]
        (val1, cur1) = paid.split(" ")
        (val2, cur2) = received.split(" ")
        val1 = -float(val1)
        val2 = float(val2)

        # currency check
        if not ((curcheck1 == cur1 and curcheck2 == cur2) or (curcheck1 == cur2 and curcheck2 == cur1)): 
          exit('ERROR: currency mismatch in Gatecoin file on line %d: (%s-%s) vs (%s-%s)' % (ln, curcheck1, curcheck2, cur1, cur2))
        # fee check
        feeMultiplier = 1.0 + float(feerate[:-1]) / 100
        total = feeMultiplier * float(offer) * float(rate)
        if abs(total + val1) > 1e-5: # ledger entries rounded by gatecoin to nearest 1e-5
          exit('ERROR: total paid mismatch in Gatecoin file on line %d: %f vs %f' % (ln, total, val1))

        return InputTX(date, cur1, val1, cur2, val2)

    else:
      exit("ERROR: Unknown file format with first line '" + firstline + "'")

    self._parseline = parseline

  def parse(self, line, ln):
    tx = self._parseline(line, ln)
    threshold = 1e-8
    if tx and abs(tx.amount1) < threshold and abs(tx.amount2) < threshold: tx = None
    return tx


class transferHandler:
  def __init__(self):
    self.transfers = {}
    self.unmatchedByDate = {}
    self.matched = {}
    self.fingerprints = {}
    self.sourcefiles = {}

  def fingerprint(self, _tx):
    # create (canonical) fingerprint
    acc1 = _tx.account1
    acc2 = _tx.account2
    amnt = round(_tx.amount2, 5)
    if amnt < 0:
      amnt = abs(amnt)
      acc1 = tx.account2
      acc2 = tx.account1
    fingerprint = "%f %s -> %s" % (amnt, acc1, acc2)
    return fingerprint

  def add(self, _tx, _id, _filename):
    self.transfers[_id] = _tx
    self.sourcefiles[_id] = _filename
    # set up 'fuzzy' date matching lookup:
    # round to day and allow one calendar day either side to match
    t = float(time.strftime("%s", time.strptime(_tx.date, "%Y-%m-%d-%H-%M")))
    ts = [
      time.strftime("%Y-%m-%d", time.gmtime(t)),
      time.strftime("%Y-%m-%d", time.gmtime(t - 60*60*24)),
      time.strftime("%Y-%m-%d", time.gmtime(t + 60*60*24))
    ]
    fingerprint = self.fingerprint(_tx)
    self.fingerprints[_id] = fingerprint
    found = False
    for t in ts:
      if t in self.unmatchedByDate:
        for pid in self.unmatchedByDate[t]:
          p = self.transfers[pid]
          if fingerprint == self.fingerprints[pid] and _filename != self.sourcefiles[pid]:
            self.unmatchedByDate[t].remove(pid)
            self.matched[pid] = _id
            self.matched[_id] = pid
            found = True
            break
      if found: break
    if not found:
      if ts[0] not in self.unmatchedByDate:
        self.unmatchedByDate[ts[0]] = []
      self.unmatchedByDate[ts[0]].append(_id)

  def isMatched(self, _id):
    return _id in self.matched

  def matchIdOf(self, _id):
    if self.isMatched(_id):
      return self.matched[_id]
    else:
      return None

  def matchOf(self, _id):
    if self.isMatched(_id):
      return self.transfers[self.matchIdOf(_id)]
    else:
      return None

  def fingerprintOf(self, _id):
    if _id in self.transfers:
      return self.fingerprints[_id]
    else:
      return None

  def sourceOf(self, _id):
    if _id in self.transfers:
      return self.sourcefiles[_id]
    else:
      return None

  def strOf(self, _id):
    return "%s (%s; %s)" % (self.fingerprints[_id], _id, self.sourcefiles[_id])

  def __str__(self):
    data = {}
    for id_ in self.transfers:
      tx = self.transfers[id_]
      if tx.date not in data: data[tx.date] = []
      s = self.strOf(id_)
      if id_ in self.matched:
        mid = self.matched[id_]
        s += " matched with " + self.strOf(mid)
      else:
        s = "UNMATCHED: " + s
      data[tx.date].append(s)

    dates = list(data.keys())
    dates.sort()

    ss = "Transfers:\n"
    for d in dates:
      for f in data[d]:
        ss += d + " " + f + "\n"
    return ss

transfers = transferHandler()

# TODO: make this list a command line input or something
currencyPriorities = {baseCurrency: 0, 'BTC': -10, 'EUR': -20, 'USD': -30, 'CHF': -40}
plevel = min(list(currencyPriorities.values())) - 10
for currency in currencyPairs.currencies():
  if currency not in currencyPriorities:
    currencyPriorities[currency] = plevel

# TODO: make this list a command line input or something
accountPrefixes = ['poloniex', 'kraken', 'bitstamp', 'gatecoin', 'localbitcoins', 'bitfinex', 'bittrex', 'cryptsy', 'btcsx', 'currencyfair', 'hsbc']

for filename in inputs:
  print("DEBUG: reading ledger file %s" % filename)

  accountPrefix = re.sub('^.*/','', re.sub('\..*$', '', filename))
  if accountPrefix not in accountPrefixes:
    accountPrefix = '' # computer says no

  print("DEBUG: using account prefix \"%s\" derived from filename" % (accountPrefix))

  with open(filename) as f:
    ln = 0
    for line in f:
      ln += 1

      if ln == 1:
        filereader = FileReader(line)
      else:
        tx = filereader.parse(line, ln)

        if not tx: continue
        if tx.date > args.end: continue

        if tx.amount1 * tx.amount2 > 0:
          exit('ERROR: Invalid fund exchange on %s line %d: %s %f <> %s %f' % (filename, ln, tx.curr1, tx.amount1, tx.curr2, tx.amount2) )

        # Process entry
        account1 = tx.account1
        account2 = tx.account2

        value1 = False;
        value2 = False;

        # determine value
        if tx.curr1 == tx.curr2:
          if tx.curr1 == baseCurrency:
            v1 = tx.amount1
            v2 = tx.amount2
          elif currencyPairs.canConvertOn(tx.date, tx.curr1, baseCurrency):
            v1 = currencyPairs.convert(tx.date, tx.curr1, baseCurrency, tx.amount1)
            v2 = currencyPairs.convert(tx.date, tx.curr2, baseCurrency, tx.amount2)
          else:
            exit('ERROR: Currency conversions for %s is not available on %s in %s at line %d' % (tx.curr1, tx.date, filename, ln))

          if tx.curr1 != baseCurrency and abs(v1) != abs(v2):
            print('WARNING: mismatched transaction values: %f vs %f on %s (line %d)' % (v1, v2, tx.date, ln))
            if v1 == 0 or v2 == 0: print('SUGGESTION: set the currency of the zero value to %s' % baseCurrency)
          value1 = math.copysign(max(abs(v1), abs(v2)), tx.amount1)
          value2 = -value1
        else:
          # determine which currency has higher priority
          tcs = (tx.curr1, tx.curr2)
          tas = (tx.amount1, tx.amount2)

          if tx.curr1 not in currencyPriorities and tx.curr2 not in currencyPriorities: i = 1
          elif tx.curr1 not in currencyPriorities: i = 2
          elif tx.curr2 not in currencyPriorities: i = 1
          else: i = (1, 2)[currencyPriorities[tx.curr1] < currencyPriorities[tx.curr2]]

          if tcs[i - 1] == baseCurrency:
            v = tas[i - 1]
          elif currencyPairs.canConvertOn(tx.date, tcs[i - 1], baseCurrency):
            v = currencyPairs.convert(tx.date, tcs[i - 1], baseCurrency, tas[i - 1])
          else:
            exit('ERROR: Currency conversions for priority currency %s is not available on %s in %s at line %d' % (tcs[i - 1], tx.date, filename, ln))

          value1 = math.copysign(v, tas[0])
          value2 = -value1

        # ignore dust transactions
        if abs(value1) < 0.001 and abs(tx.amount1) < 1e-8 and abs(tx.amount2) < 1e-8:
          continue

        # add account prefix
        if not tx.isTransfer:
          account1 = accountPrefix + account1
          account2 = accountPrefix + account2

        id_ = createTXid(account1, account2, value1, tx.date, filename + str(ln))

        # skip transfer seen from the other side
        if tx.isTransfer:
          transfers.add(tx, id_, filename)
          if transfers.isMatched(id_):
            #mid = transfers.matchIdOf(id_)
            #print("DEBUG: ignoring transfer %s, matched to %s, (line %d)" % (transfers.strOf(id_), transfers.strOf(mid), ln))
            continue

        if account1 not in accounts: 
          accounts[account1] = Account(account1, tx.curr1)
          print("DEBUG: creating account for %s" % account1)
        if account2 not in accounts: 
          accounts[account2] = Account(account2, tx.curr2)
          print("DEBUG: creating account for %s" % account2)

        if (tx.curr1 == baseCurrency and tx.amount1 != value1) or (tx.curr2 == baseCurrency and tx.amount2 != value2):
          print("DEBUG: adding cost asymmetric tx on %s: [%s :: %f %s :: %f %s] -> [%s :: %f %s :: %f %s]" % (tx.date, account1, tx.amount1, tx.curr1, value1, baseCurrency, account2, tx.amount2, tx.curr2, value2, baseCurrency))

        #print("DEBUG: {%s, %f, %f} & {%s, %f, %f}" % (account1, amount1, value1, account2, amount2, value2))
        accounts[account1].addTX(TX(tx.amount1, value1, tx.date, id_))
        accounts[account2].addTX(TX(tx.amount2, value2, tx.date, id_))

        if tx.curr1 != baseCurrency and tx.curr2 != baseCurrency:
          #print("DEBUG: {%s, %f, %f} & {%s, %f, %f}" % (baseCurrency, -value1, -value1, baseCurrency, -value2, -value2))
          accounts[baseCurrency].addTX(TX(-value1, -value1, tx.date, id_))
          accounts[baseCurrency].addTX(TX(-value2, -value2, tx.date, id_))


print('\n')

ml = 0
for curr in accounts.keys():
  l = len(curr)
  if l > ml: ml = l
ml += 1

print((" " * (ml - 7)) + "Account, \tBalance, \tCost, \t\tProfit, \tProceeds, \tChargeable")
numberDisposals = 0
totalProceeds = 0.0
finalTotalCost = 0.0
finalTotalGains = 0.0
finalTotalProfit = 0.0
initialTotalCost = 0.0
for curr in accounts.keys():
  a = accounts[curr]
  a.process()

  (proceeds, num) = a.proceedsBetween(args.start, args.end)
  profit = a.profitBetween(args.start, args.end)
  chargeable = a.chargeableBetween(args.start, args.end)
  balance = a.balanceAt(args.end)
  cost = a.costAt(args.end)

  totalProceeds += proceeds
  numberDisposals += num
  initialTotalCost += a.costAt(args.start)
  finalTotalCost += cost
  finalTotalGains += chargeable
  finalTotalProfit += profit

  print('%s%s,\t%f,\t%f,\t%f,\t%f,\t%f' % (" " * (ml - len(curr)), a.name, balance, cost, profit, proceeds, chargeable))

print('\n')

print("Final:\n  Cost = %f %s\n  Profit = %f %s\n  Proceeds = %f %s\n  Chargeable = %f %s\n  Number of disposals = %i\n" % (finalTotalCost, baseCurrency, finalTotalProfit, baseCurrency, totalProceeds, baseCurrency, finalTotalGains, baseCurrency, numberDisposals) )

error = abs(finalTotalCost - initialTotalCost)
print("Check:\n  %f (%s)\n" % (error, ("FAILED", "OK")[error < 0.01]) )

transferdatafile = open('output/transfers.txt', 'w')
transferdatafile.write(str(transfers))
transferdatafile.close()



