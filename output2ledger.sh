#!/bin/bash
#
# Concatenate all the separate account ledger files and order the entries
# into a single ledger file

echo "WARNING: check creation date of output/*.csv"
rm output/cat.csv output/cat_sorted.csv
cat output/*.csv > output/cat.csv
sort --field-separator="," -k 1,1 -k 2,2 -k 5,5 output/cat.csv > output/cat_sorted.med
echo "Date, Id, Account, Base, Value, Currency, Amount, Chargeable, Profit" > output/cat_sorted.csv
sed s/,=sum.*$// < output/cat_sorted.med >> output/cat_sorted.csv
rm output/cat_sorted.med

