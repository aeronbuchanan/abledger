#!/bin/bash

#ln -s ../../ledgers/poloniex.csv markets.poloniex.krkn
#ln -s ../../ledgers/kraken.csv markets.kraken.krkn

./conversions.py -i 'conversions/workdir/*EUR.raw' -o conversions/workdir/BTCEUR.csv -f BTC -t EUR -s 2014-01-01-00-00 
./conversions.py -i 'conversions/workdir/*USD.raw' -o conversions/workdir/BTCUSD.csv -f BTC -t USD -s 2014-01-01-00-00
./conversions.py -i conversions/workdir/googleEURGBP.dat -o conversions/EURGBP.csv -f EUR -t GBP -s 2014-01-01-00-00 
./conversions.py -i conversions/workdir/googleUSDGBP.dat -o conversions/USDGBP.csv -f USD -t GBP -s 2014-01-01-00-00 
./conversions.py -i conversions/workdir/googleBTCGBP.dat -o conversions/workdir/BTCGBP_ggl.csv -f BTC -t GBP -s 2014-01-01-00-00 
./conversions.py -i conversions/workdir/localbtcGBP.raw -o conversions/workdir/BTCGBP_lbc.csv -f BTC -t GBP -s 2014-01-01-00-00 
./conversions.py -i "conversions/workdir/market.*" -o conversions/workdir/marketsETHBTC.csv -f ETH -t BTC -s 2014-01-01-00-00

./combine.py -1 conversions/workdir/BTCEUR.csv -2 conversions/EURGBP.csv -o conversions/workdir/BTCGBP_eur.csv
./combine.py -1 conversions/workdir/BTCUSD.csv -2 conversions/USDGBP.csv -o conversions/workdir/BTCGBP_usd.csv
./conversions.py -i 'conversions/workdir/BTCGBP_*.csv' -o conversions/BTCGBP.csv -f BTC -t GBP -c robust-mean -w "0.1,0.2,1,2"

./combine.py -1 conversions/workdir/marketsETHBTC.csv -2 conversions/BTCGBP.csv -o conversions/ETHGBP.csv
./combine.py -1 conversions/workdir/XMRBTC.csv -2 conversions/BTCGBP.csv -o conversions/XMRGBP.csv

./conversions.py -i conversions/workdir/AUDGBP.csv -o conversions/AUDGBP.csv -f AUD -t GBP
./conversions.py -i conversions/workdir/CHFGBP.csv -o conversions/CHFGBP.csv -f CHF -t GBP


