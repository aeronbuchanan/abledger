#!/bin/bash
#
# Download currency data from cryptocompare

t=`date --utc +"%m/%d/%Y"`
s=`date --date $t" 18:00 UTC" +"%s"`
e=`date --date "01/01/2014 18:00 UTC" +"%s"`
d=86400

f=ETHBTCUSDEUR.csjson

mv $f $f.bak

for (( s=$(($s - $d)) ; $s >= $e ; s=$(($s - $d)) )) ; do 
  j=`curl "https://min-api.cryptocompare.com/data/pricehistorical?fsym=ETH&tsyms=BTC,USD,EUR&ts=$s"`
  t=`date --utc --date "@$s" +"%Y-%m-%d %H:%M"`
  echo $t,$j >> $f
  sleep 1
done

