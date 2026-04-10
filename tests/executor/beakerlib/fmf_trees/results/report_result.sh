#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun 'TmpDir=$(mktemp -d)' 0 "Create tmp directory"
        rlRun "pushd $TmpDir"
    rlPhaseEnd
    rlPhaseStartTest
        rlReport "some result name" FAIL
        rlRun "echo some log content > logfile.txt"
        rlReport "result name with log" PASS 0 logfile.txt
    rlPhaseEnd
    rlPhaseStartTest "some phase name"
        rlRun "/bin/false" 0 "Running false"
    rlPhaseEnd
    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $TmpDir" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalPrintText
rlJournalEnd
