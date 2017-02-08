#!/usr/bin.bash
#
# Concatenate all the separate account ledger files and order the entries
# into a single ledger file

echo WARNING: check creation date of output/*.csv 
cat output/*.csv > output/cat.csv
sort --field-separator="," -k 1,1 -k 2,2 -k 5,5 cat.csv > cat_sorted.csv


