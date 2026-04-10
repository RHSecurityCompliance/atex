#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest
        rlRun "echo some log content > log.txt"
        rlFileSubmit log.txt
        rlFileSubmit log.txt "custom log name.txt"
    rlPhaseEnd
rlJournalPrintText
rlJournalEnd
