#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

case "$1" in
    before)
        before_cmd=(rlRun "/bin/false" 0 "Running false before reboot")
        after_cmd=(rlRun "/bin/true" 0 "Running true after reboot")
        ;;
    after)
        before_cmd=(rlRun "/bin/true" 0 "Running true before reboot")
        after_cmd=(rlRun "/bin/false" 0 "Running false after reboot")
        ;;
esac

rlJournalStart
    if [[ $TMT_REBOOT_COUNT -eq 0 ]]; then
        rlPhaseStartTest
            "${before_cmd[@]}"
            rlPhaseEnd
            rhts-reboot
        rlPhaseEnd
    else
        rlPhaseStartTest
            "${after_cmd[@]}"
        rlPhaseEnd
    fi
rlJournalPrintText
rlJournalEnd
