#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest
        rlRun "rlImport yum/common-functions"
        rlRun "yumlibIsDnf5" 0,1
    rlPhaseEnd
rlJournalPrintText
rlJournalEnd
