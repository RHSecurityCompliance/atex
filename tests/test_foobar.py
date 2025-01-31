from atex import util

def testme():
    print("testme!")
    util.info("testme via info!")

def _hidden_testme():
    print("hidden_testme!")
    util.info("hidden_testme via info!")

def second_testme():
    print("second_testme!")
    util.info("second_testme via info!")
