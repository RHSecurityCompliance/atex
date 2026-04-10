#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

reboot_cmd=$1

rlJournalStart
    if [[ $TMT_REBOOT_COUNT -eq 0 ]]; then
        rlPhaseStartTest
            rlRun "/bin/true" 0 "Running true before reboot"
            rlPhaseEnd
            $reboot_cmd
        rlPhaseEnd
    else
        rlPhaseStartTest
            rlRun "/bin/true" 0 "Running true after reboot"
        rlPhaseEnd
    fi
rlJournalPrintText
rlJournalEnd
