#!/bin/bash
#
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2014 The moOde audio player project / Tim Curtis
# Copyright 2025 MoodeOled project / Benoit Toufflet

READY_CHIME_URI="$1"
READY_CHIME_TITLE="$2"
WAIT_SECS="$3"
MOODE_LOG="/var/log/moode.log"

moode_log () {
	echo "$1"
	TIME=$(date +'%Y%m%d %H%M%S')
	echo "$TIME ready-script: $1" >> $MOODE_LOG
}

# Begin
moode_log "Started"

# Wait before continuing
moode_log "Wait $WAIT_SECS seconds..."
sleep $WAIT_SECS

# Start the OLED display service instead of playing the chime
moode_log "Start nowoled.service"
systemctl start nowoled

# Done
moode_log "Finished"
exit 0
