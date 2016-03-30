#!/bin/bash

defaultfiler=opw-filervault
defaultuser=root
filers="opw-filer01 opw-filer02 opw-filer03 opw-filer04 opw-filer05 opw-filervault"

isinlist() {
	item=$1
	shift 1
	for tmp in $@
	do
		test "$tmp" == "$item" && return 0
	done
	return 1
}

run() {
	filer=${1:-$defaultfiler}
	user=${2:-$defaultuser}
	shift 2
	rsh -l $user $filer $@
	return $?
}

abletorun() {
	filer=${1:-$defaultfiler}
	user=${2:-$defaultuser}
	run $filer $user snapmirror status > /dev/null 2>&1
	return $?
}

aggrlist() {
	filer=${1:-$defaultfiler}
	user=${2:-$defaultuser}
	run $filer $user aggr status | sed -n "s|^\s*\(\w*\)\s*online.*|\1|p"
	return $?
}

vollist() {
	aggr=$1
	filer=${2:-$defaultfiler}
	user=${3:-$defaultuser}
	if [ -z "$aggr" ]; then
		run $filer $user vol status | sed -n "s|^\s*\(\w*\)\s*online.*|\1|p"
	else
		for tmp in `aggrlist`
		do
			if [ "$tmp" == "$aggr" ]; then
				run $filer $user aggr status -v $tmp | grep "Volumes:" -A100 | grep "Plex" -B100 | sed -e "s|.*Plex.*||" -e "s|Volumes:||" -e "s|^\s*||g" -e "s|,\s*|\n|g" | sed "/^$/d"
			fi
		done
	fi
	return $?
}

volsize() {
	filer=${1:-$defaultfiler}
	volume=$2
	user=${3:-$defaultuser}
	run $filer $user vol size $volume | sed -n "s|^.*has size \(\w*\)\.|\1|p"
	return $?
}

snaplist () {
	filer=${1:-$defaultfiler}
	volume=$2
	user=${3:-$defaultuser}
	IFS_OLD=$IFS
	IFS=$'\n'
	for snapshot in `run $filer $user snap list -n $volume | grep -A100 '\-\-\-\-\-\-\-\-\-\-\-\-' | grep -v  '\-\-\-\-\-\-\-\-\-\-\-\-' | sed "s|\s(.*)$||" | tac`
	do
		snapdate=${snapshot:4:2}${snapshot:0:3}${snapshot:7:2}${snapshot:10:2}
		snapname=${snapshot:14}
		echo $snapdate-$snapname
	done
	IFS=$IFS_OLD
}	

qtreelist() {
	filer=${1:-$defaultfiler}
	volume=$2
	user=${3:-$defaultuser}
	IFS_OLD=$IFS
	IFS=$'\n'
	for qtree in `run $filer $user qtree status $volume | grep "$volume"`
	do
		tmp=`echo -n $qtree | sed -e "s|\s*\w*\s\s\w*\s\s\w*\s*$||" -e "s|^\w*\s*||"`
		test -z "$tmp" && tmp="-"
		echo $tmp
	done
	IFS=$IFS_OLD
}


src="$1"
dst="$2"
user=${3:-$defaultuser}

if [[ $src == *:* ]]; then
	srcfiler=${src%%:*}
	src=${src#*:}
else
	srcfiler=$defaultfiler
fi
if [[ $src == */* ]]; then
	src=${src#/vol/*}
	srcvolume=${src%/*}
#	src=${src#*/}
else
	srcvolume=$src
fi
if [[ $src == */* ]]; then
	srcqtree=${src#*/}
else
	srcqtree=-
fi

if [[ $dst == *:* ]]; then
	dstfiler=${dst%%:*}
	dst=${dst#*:}
else
	dstfiler=$srcfiler
fi
if [[ $dst == */* ]]; then
	dst=${dst#/vol/*}
	dstvolume=${dst%/*}
#	dst=${dst#*/}
else
	dstvolume=$dst
fi
if [[ $dst == */* ]]; then
	dstqtree=${dst#*/}
else
	dstqtree=-
fi
echo "You are about to transfer all Snapshot Qtree data from $srcfiler:/vol/$srcvolume/$srcqtree to $dstfiler:/vol/$dstvolume/$dstqtree"
read -p "Do you wish to continue? (y/N): " answer

tmp=$(echo ${answer:0:1} | tr "Y" "y")
test "$tmp" == "y" || exit 0


if isinlist $srcfiler $filers
then
	if ! abletorun $srcfiler $user
	then
		echo "Unable to run commands on filer $srcfiler" 1>&2
		exit 2
	fi
else
	echo "$srcfiler in not a valid filer." 1>&2
	exit 1
fi

if isinlist $dstfiler $filers
then
	if ! abletorun $dstfiler $user
	then
		echo "Unable to run commands on filer $dstfiler" 1>&2
		exit 2
	fi
else
	echo "$dstfiler in not a valid filer." 1>&2
	exit 1
fi

if ! [ "`volsize $srcfiler $srcvolume $user`" == "`volsize $dstfiler $dstvolume $user`" ]; then
	echo "Volumes $srcfiler:/vol/$srcvolume and $dstfiler:/vol/$dstvolume are not the same size!" 1>&2
	exit 3
fi

if ! isinlist $srcqtree `qtreelist $srcfiler $srcvolume $user`
then
	echo "$srcfiler:/vol/$srcvolume/$srcqtree is not a valid Qtree path." 1>&2
	exit 4
fi

if isinlist $dstqtree `qtreelist $dstfiler $dstvolume $user`
then
	echo "The Qtree path $dstfiler:/vol/$dstvolume/$dstqtree already exists." 1>&2
	exit 4
fi

firstrun=0
begintime=$(date +%s)
for newsnapshot in `snaplist $srcfiler $srcvolume $user`
do
	starttime=$(date +%s)
	oldsnapshot=${newsnapshot:10}
	tmpsnapshot="migrate.$oldsnapshot"

	run $srcfiler $user snap rename $srcvolume $oldsnapshot $tmpsnapshot
	operation="update"
	if [ "$firstrun" == "0" ]; then
		firstrun=1
		operation="initialize"
	fi
	echo "Mirroring $srcfiler:/vol/$srcvolume/$srcqtree -snapshot $tmpsnapshot --> $dstfiler:/vol/$dstvolume/$dstqtree -snapshot $newsnapshot"
	run $dstfiler $user snapmirror $operation -S $srcfiler:/vol/$srcvolume/$srcqtree -s $tmpsnapshot -c $newsnapshot -w $dstfiler:/vol/$dstvolume/$dstqtree
	run $srcfiler $user snap rename $srcvolume $tmpsnapshot $oldsnapshot 

	endtime=$(date +%s)

	echo -e "Operation took $(( $endtime - $starttime)) seconds.\n"
done

run $dstfiler $user snapmirror quiesce $dstfiler:/vol/$dstvolume/$dstqtree
run $dstfiler $user snapmirror break -f $dstfiler:/vol/$dstvolume/$dstqtree

endtime=$(date +%s)
echo -e "Entire transfer took $(( $endtime - $begintime)) seconds.\n"

exit $?

