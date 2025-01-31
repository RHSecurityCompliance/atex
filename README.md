# ATEX = Ad-hoc Test EXecutor

A collections of Python APIs to provision operating systems, collect
and execute [FMF](https://github.com/teemtee/fmf/)-style tests, gather
and organize their results and generate reports from those results.

The name comes from a (fairly unique to FMF/TMT ecosystem) approach that
allows provisioning a pool of systems and scheduling tests on them as one would
on an ad-hoc pool of thread/process workers - once a worker becomes free,
it receives a test to run.  
This is in contrast to splitting a large list of N tests onto M workers
like N/M, which yields significant time penalties due to tests having
very varies runtimes.

Above all, this project is meant to be a toolbox, not a silver-plate solution.
Use its Python APIs to build a CLI tool for your specific use case.  
The CLI tool provided here is just for demonstration / testing, not for serious
use - we want to avoid huge modular CLIs for Every Possible Scenario. That's
the job of the Python API. Any CLI should be simple by nature.

---

THIS PROJECT IS HEAVILY WIP, THINGS WILL MOVE AROUND, CHANGE AND OTHERWISE
BREAK. DO NOT USE IT (for now).

---

## License

Unless specified otherwise, any content within this repository is distributed
under the GNU GPLv3 license, see the [COPYING.txt](COPYING.txt) file for more.

## Unsorted notes

```
- this is not tmt, the goal is to make a python toolbox *for* making runcontest
  style tools easily, not to replace those tools with tmt-style CLI syntax

  - the whole point is to make usecase-targeted easy-to-use tools that don't
    intimidate users with 1 KB long command line, and runcontest is a nice example

  - TL;DR - use a modular pythonic approach, not a modular CLI like tmt


- Orchestrator with
  - add_provisioner(<class>, max_workers=1)   # will instantiate <class> at most max_workers at a time
  - algo
    - for all provisioner classes, spawns classes*max_workers as new Threads
    - waits for any .reserve() to return
    - creates a new Thread for minitmt, gives it p.get_ssh() details
      - minitmt will
        - establish a SSHConn
        - install test deps, copy test repo over, prepare socket dir on SUT, etc.
        - run the test in the background as
            f=os.open('some/test/log', os.WRONLY); subprocess.Popen(..., stdout=f, stderr=f, stdin=subprocess.DEVNULL)
        - read/process Unix sock results in the foreground, non-blocking,
          probably calling some Orchestrator-provided function to store results persistently
        - regularly check Popen proc status, re-accept UNIX sock connection, etc., etc.
      - minitmt also has some Thread-independent way to .cancel(), killing the proc, closing SSHConn, etc.

  - while waiting for minitmt Threads to finish, to re-assign existing Provisioner instances
    to new minitmt Threads, .. Orchestrator uses some logic to select, which TestRun
    would be ideal to run next
    - TestRun probably has some "fitness" function that returns some priority number
      when given a Provisioner instance (?) ...
    - something from minitmt would also have access to the Provisioner instance
    - the idea is to allow some logic to set "hey I set up nested VM snapshot on this thing"
      on the Provisioner instance, and if another /hardening/oscap TestRun finds
      a Provisioner instance like that, it would return high priority
    - ...
    - similar to "fitness" like function, we need some "applicability" function
      - if TestRun is mixed to RHEL-9 && x86_64, we need it to return True
        for a Provisioner instance that provides RHEL-9 and x86_64, but False otherwise

- basically Orchestrator has
  - .add_provisioner()
  - .run_test()  # called with an exclusively-borrowed Provisioner instance
    - if Provisioner is_alive()==False after .run_test(), instantiate a new one from the same inst.__class__
    - if test failed and reruns > 0, try run_test() again (or maybe re-queue the test)
  - .output_result()  # called by run_test() to persistently log a test result
  - .applicable()  # return True if a passed TestRun is meant for a passed Platform (Provisioner?)
    - if no TestRun returns True, the Provisioner is .release()d because we don't need it anymore
  - .fitness()    # return -inf / 0 / +inf with how much should a passed TestRun run on a Provisioner
  - MAYBE combine applicable() and fitness() into one function, next_test() ?
    - given the free Provisioner and a list of TestRuns, select which should run next on the Provisioner
      - if none is chosen, .release() the Provisioner without replacement, continue
```
