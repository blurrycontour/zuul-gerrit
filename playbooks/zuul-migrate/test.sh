#!/bin/bash

source /home/zuul/functions

setup_temp_space

change_list_file=$MYTMPDIR/change_list.txt

cp ~/data $change_list_file

RELEASE_META="something"

while read deliverable series version diff_start repo hash pypi first_full; do
    echo "$deliverable $series $version $diff_start $repo $hash $pypi $first_full"
    ~/test2.sh $deliverable $series $version $diff_start $repo $hash $pypi $first_full "$RELEASE_META"
done < $change_list_file

exit 1
