#!/bin/bash
#
# Download currency data from cryptocompare

t=`date --utc +"%m/%d/%Y"`
s=`date --date $t" 12:00 UTC" +"%s"`
e=`date --date "01/01/2014 12:00 UTC" +"%s"`
d=86400

from=ETH
to1=BTC
to2=USD
to3=EUR

f=$from$to1$to2$to3.csjson

mv $f $f.bak

for (( s=$(($s - $d)) ; $s >= $e ; s=$(($s - $d)) )) ; do 
  j=`curl "https://min-api.cryptocompare.com/data/pricehistorical?fsym=$from&tsyms=$to1,$to2,$to3&ts=$s"`
  t=`date --utc --date "@$s" +"%Y-%m-%d %H:%M"`
  echo $t,$j >> $f
  sleep 1
done

