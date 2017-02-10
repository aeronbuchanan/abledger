#!/bin/bash
#
# Download currency data from kraken

e=`date --date "01/01/2014 18:00 UTC" +"%s"`
f=krakenXETHXXBT.json

mv $f $f.bak

curl "https://api.kraken.com/0/public/OHLC?pair=XETHXXBT&interval=60&since=$e" > $f


