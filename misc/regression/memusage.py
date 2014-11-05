#!/usr/bin/env python
#
#
# Copyright 2014, NICTA
#
# This software may be distributed and modified according to the terms of
# the BSD 2-Clause license. Note that NO WARRANTY is provided.
# See "LICENSE_BSD2.txt" for details.
#
# @TAG(NICTA_BSD)
#

'''
Monitors the peak memory usage of a process and its children. Usage is similar
to the UNIX `time` utility.
'''
import psutil, subprocess, sys, threading, time

def get_usage(proc):
    '''Retrieve the memory usage of a particular psutil process without its
    children. We use the proportional set size, which accounts for shared pages
    to give us a more accurate total usage.'''
    assert isinstance(proc, psutil.Process)
    return sum([m.pss for m in proc.get_memory_maps(grouped=True)])

def get_total_usage(pid):
    '''Retrieve the memory usage of a process by PID including its children. We
    ignore NoSuchProcess errors to mask subprocesses exiting while the cohort
    continues.'''
    total = 0
    try:
        p = psutil.Process(pid)
        total += get_usage(p)
    except psutil.NoSuchProcess:
        return 0
    for proc in p.get_children(recursive=True): #pylint: disable=E1123
        try:
            total += get_usage(proc)
        except psutil.NoSuchProcess:
            pass
    return total

class Poller(threading.Thread):
    def __init__(self, pid):
        super(Poller, self).__init__()
        # Daemonise ourselves to avoid delaying exit of the process of our
        # calling thread.
        self.daemon = True
        self.pid = pid
        self.high = 0
        self.finished = False

    def run(self):
        self.high = 0
        # Poll the process once a second and track a high water mark of its
        # memory usage.
        while not self.finished:
            usage = get_total_usage(self.pid)
            if usage > self.high:
                self.high = usage
            time.sleep(1)

    def peak_mem_usage(self):
        return self.high

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.finished = True

def process_poller(pid):
    '''Initiate polling of a subprocess. This is intended to be used in a
    `with` block.'''
    p = Poller(pid)
    p.start()
    return p

def main():
    if len(sys.argv) <= 1 or sys.argv[1] in ['-?', '--help']:
        print >>sys.stderr, 'Usage: %s command args...\n Measure peak memory ' \
            'usage of a command' % sys.argv[0]
        return -1

    # Run the command requested.
    try:
        p = subprocess.Popen(sys.argv[1:])
    except OSError:
        print >>sys.stderr, 'command not found'
        return -1

    high = 0
    try:
        with process_poller(p.pid) as m: #pylint: disable=E1101
            p.communicate()
            high = m.peak_mem_usage()
    except KeyboardInterrupt:
        # The user Ctrl-C-ed us. Fake an error return code.
        p.returncode = -1

    print >>sys.stderr, 'Peak usage %d bytes' % high

    return p.returncode

if __name__ == '__main__':
    sys.exit(main())