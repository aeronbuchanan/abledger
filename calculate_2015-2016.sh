#!/bin/bash

./kraken2transfers.py
./polo2transfers.py
./abledger.py -a ledgers/accounts2015-2016.dat -i "ledgers/*.csv" -c "conversions/*.csv" -s 2015-04-06-00-05 -e 2016-04-05-23-55
