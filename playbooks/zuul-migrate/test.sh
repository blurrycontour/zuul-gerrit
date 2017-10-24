#!/bin/bash

source functions

setup_temp_space

change_list_file=$MYTMPDIR/change_list.txt

echo "1" > $change_list_file
echo "2" > $change_list_file
echo "3" > $change_list_file

while read foo; do
    echo "$foo"
    ~/test2.sh
done < $change_list_file

exit 1
