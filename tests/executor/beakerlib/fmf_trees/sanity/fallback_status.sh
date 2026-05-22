#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest
        case "$1" in
            pass)
                rlRun "/bin/true" 0 "Running true"
                ;;
            fail)
                # do a pass first, simulating other results in the test
                rlRun "/bin/true" 0 "Running true"
                rlRun "/bin/false" 0 "Running false"
                ;;
            exit)
                # exit before any rlPhaseEnd reports a result
                exit 123
                ;;
        esac
    rlPhaseEnd
rlJournalPrintText
rlJournalEnd
