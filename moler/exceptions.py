# -*- coding: utf-8 -*-
__author__ = 'Grzegorz Latuszek'
__copyright__ = 'Copyright (C) 2018, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com'


class WrongUsage(Exception):
    """Wrong usage of library"""
    pass


# TODO: do we need it? Just mapping to asyncio/concurrent.futures naming?
class CancelledError(Exception):
    pass


class NoResultSinceCancelCalled(CancelledError):
    def __init__(self, connection_observer):
        """Create instance of NoResultSinceCancelCalled exception"""
        err_msg = 'for {}'.format(connection_observer)
        super(NoResultSinceCancelCalled, self).__init__(err_msg)
        self.connection_observer = connection_observer


# TODO: do we need it? Just mapping to asyncio naming?
class InvalidStateError(Exception):
    pass


class ResultNotAvailableYet(InvalidStateError):
    def __init__(self, connection_observer):
        """Create instance of ResultNotAvailableYet exception"""
        err_msg = 'for {}'.format(connection_observer)
        super(ResultNotAvailableYet, self).__init__(err_msg)
        self.connection_observer = connection_observer


class ConnectionObserverNotStarted(InvalidStateError):
    def __init__(self, connection_observer):
        """Create instance of ConnectionObserverNotStarted exception"""
        err_msg = 'for {}'.format(connection_observer)
        super(ConnectionObserverNotStarted, self).__init__(err_msg)
        self.connection_observer = connection_observer


class ResultAlreadySet(InvalidStateError):
    def __init__(self, connection_observer):
        """Create instance of ResultAlreadySet exception"""
        err_msg = 'for {}'.format(connection_observer)
        super(ResultAlreadySet, self).__init__(err_msg)
        self.connection_observer = connection_observer


class ConnectionObserverTimeout(Exception):
    def __init__(self, connection_observer, timeout,
                 kind='run', passed_time=''):
        """Create instance of ConnectionObserverTimeout exception"""
        if passed_time:
            passed_time = '{:.2f} '.format(passed_time)
        err_msg = '{} {} time {}>= {:.2f} sec'.format(connection_observer, kind,
                                                      passed_time, timeout)
        super(ConnectionObserverTimeout, self).__init__(err_msg + ' timeout')
        self.connection_observer = connection_observer
        self.timeout = timeout


class NoCommandStringProvided(Exception):
    def __init__(self, command):
        """Create instance of NoCommandStringProvided exception"""
        fix_info = 'fill .command_string member before starting command'
        err_msg = 'for {}\nYou should {}'.format(command, fix_info)
        super(NoCommandStringProvided, self).__init__(err_msg)
        self.command = command


class NoConnectionProvided(Exception):
    def __init__(self, connection_observer):
        """Create instance of NoConnectionProvided exception"""
        err_msg = 'for {}'.format(connection_observer)
        super(NoConnectionProvided, self).__init__(err_msg)
        self.connection_observer = connection_observer
