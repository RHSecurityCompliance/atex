#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest
        rlRun "rlImport example/file"
        rlRun "fileCreate somefile"
        rlAssertExists somefile
    rlPhaseEnd
rlJournalPrintText
rlJournalEnd
