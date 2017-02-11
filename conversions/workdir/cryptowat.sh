#!/bin/bash
#
# Download currency data from kraken

s=`date --utc --date "01/01/2014 00:00 UTC" +"%s"`
m=poloniex
F=ETC
T=BTC

f=`echo $F | awk '{print tolower($0)}'`
t=`echo $T | awk '{print tolower($0)}'`

n=cryptowat.$m$F$T.json

mv $n $n.bak

curl "https://api.cryptowat.ch/markets/$m/$f$t/ohlc?after=$s&periods=3600,21600,43200,86400" > $n



