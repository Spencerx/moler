# -*- coding: utf-8 -*-
"""
threaded.network_down_detectors_no_runner.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A fully-functional connection-observer using socket & threading.
Works on Python 2.7 as well as on 3.6

This is Layer_2 (half of it) example:
uses Moler provided external-IO TCP implementation (moler.io.raw.tcp.ThradedTcp)
that integrates with Moler's connection

This example demonstrates multiple connection observers working
on multiple connections.

Shows following concepts:
- multiple observers may observe single connection
- each one is focused on different data (processing decomposition)
- client code may run observers on different connections
- client code may "start" observers in sequence
"""
import socket
import select
import threading
from contextlib import closing

import logging
import sys
import time

from moler.connection_observer import ConnectionObserver
from moler.connection import ObservableConnection
from moler.io.raw import tcp

__author__ = 'Grzegorz Latuszek'
__copyright__ = 'Copyright (C) 2018, Nokia'
__email__ = 'grzegorz.latuszek@nokia.com'

ping_output = '''
greg@debian:~$ ping 10.0.2.15
PING 10.0.2.15 (10.0.2.15) 56(84) bytes of data.
64 bytes from 10.0.2.15: icmp_req=1 ttl=64 time=0.080 ms
64 bytes from 10.0.2.15: icmp_req=2 ttl=64 time=0.037 ms
64 bytes from 10.0.2.15: icmp_req=3 ttl=64 time=0.045 ms
ping: sendmsg: Network is unreachable
ping: sendmsg: Network is unreachable
ping: sendmsg: Network is unreachable
64 bytes from 10.0.2.15: icmp_req=7 ttl=64 time=0.123 ms
64 bytes from 10.0.2.15: icmp_req=8 ttl=64 time=0.056 ms
'''


def ping_sim_tcp_server(server_port, ping_ip, client, address):
    _, client_port = address
    logger = logging.getLogger('threaded.ping.tcp-server({} -> {})'.format(server_port,
                                                                           client_port))
    logger.debug('connection accepted - client at tcp://{}:{}'.format(*address))
    ping_out = ping_output.replace("10.0.2.15", ping_ip)
    ping_lines = ping_out.splitlines(True)
    with closing(client):
        for ping_line in ping_lines:
            data = ping_line.encode(encoding='utf-8')
            try:
                client.sendall(data)
            except socket.error:  # client is gone
                break
            time.sleep(1)  # simulate delay between ping lines
    logger.info('Connection closed')


def server_loop(server_port, server_socket, ping_ip, done_event):
    logger = logging.getLogger('threaded.ping.tcp-server({})'.format(server_port))
    while not done_event.is_set():
        # without select we can't break loop from outside (via done_event)
        # since .accept() is blocking
        read_sockets, _, _ = select.select([server_socket], [], [], 0.1)
        if not read_sockets:
            continue
        client_socket, client_addr = server_socket.accept()
        client_socket.setblocking(1)
        client_thread = threading.Thread(target=ping_sim_tcp_server,
                                         args=(server_port, ping_ip,
                                               client_socket, client_addr))
        client_thread.start()
    logger.debug("Ping Sim: ... bye")


def start_ping_sim_server(server_address, ping_ip):
    """Run server simulating ping command output, this is one-shot server"""
    _, server_port = server_address
    logger = logging.getLogger('threaded.ping.tcp-server({})'.format(server_port))
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(server_address)
    server_socket.listen(1)
    logger.debug("Ping Sim started at tcp://{}:{}".format(*server_address))
    done_event = threading.Event()
    server_thread = threading.Thread(target=server_loop,
                                     args=(server_port, server_socket, ping_ip,
                                           done_event))
    server_thread.start()
    return server_thread, done_event


def main(connections2observe4ip):
    # Starting the servers
    servers = []
    for address, ping_ip in connections2observe4ip:
        # simulate pinging given IP
        server_thread, server_done = start_ping_sim_server(address, ping_ip)
        servers.append((server_thread, server_done))
    # Starting the clients
    connections = []
    for address, ping_ip in connections2observe4ip:
        host, port = address
        # 1. create Moler's connection that knows encoding
        decoder = lambda data: data.decode("utf-8")
        moler_conn = ObservableConnection(decoder=decoder)
        # 2. create external-IO connection gluing to Moler's connection
        conn_logger_name = 'threaded.tcp-connection({}:{})'.format(*address)
        conn_logger = logging.getLogger(conn_logger_name)
        tcp_connection = tcp.ThreadedTcp(moler_connection=moler_conn,
                                         port=port, host=host,
                                         logger=conn_logger)
        client_thread = threading.Thread(target=ping_observing_task,
                                         args=(tcp_connection, ping_ip))
        client_thread.start()
        connections.append(client_thread)
    # await observers job to be done
    for client_thread in connections:
        client_thread.join()
    # stop servers
    for server_thread, server_done in servers:
        server_done.set()
        server_thread.join()


# ===================== Moler's connection-observer usage ======================
class NetworkToggleDetector(ConnectionObserver):
    def __init__(self, net_ip, detect_pattern, detected_status):
        super(NetworkToggleDetector, self).__init__()
        self.net_ip = net_ip
        self.detect_pattern = detect_pattern
        self.detected_status = detected_status
        self.logger = logging.getLogger('moler.{}'.format(self))

    def data_received(self, data):
        """Awaiting ping output change"""
        if not self.done():
            if self.detect_pattern in data:
                when_detected = time.time()
                self.logger.debug("Network {} {}!".format(self.net_ip,
                                                          self.detected_status))
                self.set_result(result=when_detected)


class NetworkDownDetector(NetworkToggleDetector):
    """
    Awaiting change like:
    64 bytes from 10.0.2.15: icmp_req=3 ttl=64 time=0.045 ms
    ping: sendmsg: Network is unreachable
    """
    def __init__(self, net_ip):
        detect_pattern = "Network is unreachable"
        detected_status = "is down"
        super(NetworkDownDetector, self).__init__(net_ip,
                                                  detect_pattern,
                                                  detected_status)


class NetworkUpDetector(NetworkToggleDetector):
    def __init__(self, net_ip):
        detect_pattern = "bytes from {}".format(net_ip)
        detected_status = "is up"
        super(NetworkUpDetector, self).__init__(net_ip,
                                                detect_pattern,
                                                detected_status)


def ping_observing_task(ext_io_connection, ping_ip):
    """
    Here external-IO connection is abstract - we don't know its type.
    What we know is just that it has .moler_connection attribute.
    """
    logger = logging.getLogger('moler.user.app-code')
    conn_addr = str(ext_io_connection)

    # Layer 2 of Moler's usage (ext_io_connection):
    # 1. create observers
    net_down_detector = NetworkDownDetector(ping_ip)
    net_drop_found = False
    net_up_detector = NetworkUpDetector(ping_ip)
    moler_conn = ext_io_connection.moler_connection
    # 2. virtually "start" observer by making it data-listener
    moler_conn.subscribe(net_down_detector.data_received)

    info = '{} on {} using {}'.format(ping_ip, conn_addr, net_down_detector)
    logger.debug('observe ' + info)

    with ext_io_connection:
        observing_timeout = 10
        start_time = time.time()
        while time.time() < start_time + observing_timeout:
            # anytime new data comes it may change status of observer
            if not net_drop_found and net_down_detector.done():
                net_drop_found = True
                net_down_time = net_down_detector.result()
                timestamp = time.strftime("%H:%M:%S", time.localtime(net_down_time))
                logger.debug('Network {} is down from {}'.format(ping_ip, timestamp))
                # 3. virtually "stop" that observer
                moler_conn.unsubscribe(net_down_detector.data_received)
                # 4. and start subsequent one (to know when net is back "up")
                info = '{} on {} using {}'.format(ping_ip, conn_addr, net_up_detector)
                logger.debug('observe ' + info)
                moler_conn.subscribe(net_up_detector.data_received)
            if net_up_detector.done():
                net_up_time = net_up_detector.result()
                timestamp = time.strftime("%H:%M:%S", time.localtime(net_up_time))
                logger.debug('Network {} is back "up" from {}'.format(ping_ip, timestamp))
                # 5. virtually "stop" that observer
                moler_conn.unsubscribe(net_up_detector.data_received)
                break
            time.sleep(0.2)


# ==============================================================================
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s |%(name)-40s |%(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stderr,
    )
    connections2observe4ip = [(('localhost', 5671), '10.0.2.15'),
                              (('localhost', 5672), '10.0.2.16')]
    main(connections2observe4ip)

'''
LOG OUTPUT

12:06:50 |threaded.ping.tcp-server(5671)           |Ping Sim started at tcp://localhost:5671
12:06:50 |threaded.ping.tcp-server(5672)           |Ping Sim started at tcp://localhost:5672
12:06:50 |moler.user.app-code                      |observe 10.0.2.15 on tcp://localhost:5671 using NetworkDownDetector(id:46425312)
12:06:50 |moler.user.app-code                      |observe 10.0.2.16 on tcp://localhost:5672 using NetworkDownDetector(id:46425704)
12:06:50 |threaded.tcp-connection(localhost:5671)  |connecting to tcp://localhost:5671
12:06:50 |threaded.tcp-connection(localhost:5672)  |connecting to tcp://localhost:5672
12:06:50 |threaded.tcp-connection(localhost:5671)  |connection tcp://localhost:5671 is open
12:06:50 |threaded.ping.tcp-server(5671 -> 62735)  |connection accepted - client at tcp://127.0.0.1:62735
12:06:50 |threaded.tcp-connection(localhost:5672)  |connection tcp://localhost:5672 is open
12:06:50 |threaded.tcp-connection(localhost:5671)  |< b'\n'
12:06:50 |threaded.ping.tcp-server(5672 -> 62736)  |connection accepted - client at tcp://127.0.0.1:62736
12:06:50 |threaded.tcp-connection(localhost:5672)  |< b'\n'
12:06:51 |threaded.tcp-connection(localhost:5672)  |< b'greg@debian:~$ ping 10.0.2.16\n'
12:06:51 |threaded.tcp-connection(localhost:5671)  |< b'greg@debian:~$ ping 10.0.2.15\n'
12:06:52 |threaded.tcp-connection(localhost:5672)  |< b'PING 10.0.2.16 (10.0.2.16) 56(84) bytes of data.\n'
12:06:52 |threaded.tcp-connection(localhost:5671)  |< b'PING 10.0.2.15 (10.0.2.15) 56(84) bytes of data.\n'
12:06:53 |threaded.tcp-connection(localhost:5672)  |< b'64 bytes from 10.0.2.16: icmp_req=1 ttl=64 time=0.080 ms\n'
12:06:53 |threaded.tcp-connection(localhost:5671)  |< b'64 bytes from 10.0.2.15: icmp_req=1 ttl=64 time=0.080 ms\n'
12:06:54 |threaded.tcp-connection(localhost:5672)  |< b'64 bytes from 10.0.2.16: icmp_req=2 ttl=64 time=0.037 ms\n'
12:06:54 |threaded.tcp-connection(localhost:5671)  |< b'64 bytes from 10.0.2.15: icmp_req=2 ttl=64 time=0.037 ms\n'
12:06:55 |threaded.tcp-connection(localhost:5672)  |< b'64 bytes from 10.0.2.16: icmp_req=3 ttl=64 time=0.045 ms\n'
12:06:55 |threaded.tcp-connection(localhost:5671)  |< b'64 bytes from 10.0.2.15: icmp_req=3 ttl=64 time=0.045 ms\n'
12:06:56 |threaded.tcp-connection(localhost:5672)  |< b'ping: sendmsg: Network is unreachable\n'
12:06:56 |moler.NetworkDownDetector(id:46425704)   |Network 10.0.2.16 is down!
12:06:56 |moler.user.app-code                      |Network 10.0.2.16 is down from 12:06:56
12:06:56 |moler.user.app-code                      |observe 10.0.2.16 on tcp://localhost:5672 using NetworkUpDetector(id:46426096)
12:06:56 |threaded.tcp-connection(localhost:5671)  |< b'ping: sendmsg: Network is unreachable\n'
12:06:56 |moler.NetworkDownDetector(id:46425312)   |Network 10.0.2.15 is down!
12:06:56 |moler.user.app-code                      |Network 10.0.2.15 is down from 12:06:56
12:06:56 |moler.user.app-code                      |observe 10.0.2.15 on tcp://localhost:5671 using NetworkUpDetector(id:46425480)
12:06:57 |threaded.tcp-connection(localhost:5672)  |< b'ping: sendmsg: Network is unreachable\n'
12:06:57 |threaded.tcp-connection(localhost:5671)  |< b'ping: sendmsg: Network is unreachable\n'
12:06:58 |threaded.tcp-connection(localhost:5672)  |< b'ping: sendmsg: Network is unreachable\n'
12:06:58 |threaded.tcp-connection(localhost:5671)  |< b'ping: sendmsg: Network is unreachable\n'
12:06:59 |threaded.tcp-connection(localhost:5672)  |< b'64 bytes from 10.0.2.16: icmp_req=7 ttl=64 time=0.123 ms\n'
12:06:59 |moler.NetworkUpDetector(id:46426096)     |Network 10.0.2.16 is up!
12:06:59 |threaded.tcp-connection(localhost:5671)  |< b'64 bytes from 10.0.2.15: icmp_req=7 ttl=64 time=0.123 ms\n'
12:06:59 |moler.NetworkUpDetector(id:46425480)     |Network 10.0.2.15 is up!
12:06:59 |moler.user.app-code                      |Network 10.0.2.15 is back "up" from 12:06:59
12:06:59 |threaded.tcp-connection(localhost:5671)  |connection tcp://localhost:5671 is closed
12:06:59 |moler.user.app-code                      |Network 10.0.2.16 is back "up" from 12:06:59
12:06:59 |threaded.tcp-connection(localhost:5672)  |connection tcp://localhost:5672 is closed
12:07:00 |threaded.ping.tcp-server(5671)           |Ping Sim: ... bye
12:07:00 |threaded.ping.tcp-server(5672)           |Ping Sim: ... bye
12:07:01 |threaded.ping.tcp-server(5672 -> 62736)  |Connection closed
12:07:01 |threaded.ping.tcp-server(5671 -> 62735)  |Connection closed
'''
