#!/usr/bin/env python 2.7
from __future__ import division

"""FC3D.py: Sends files and commands to 3D printers * ONLY tested with QIDI Printers NOT tested with other brands. """
"""Code Refactored by gekitsu"""

__author__ = "Isrever"

#IMPORTS
import time
import logging
import os
from socket import socket, AF_INET, SOCK_DGRAM, SOL_SOCKET, SO_BROADCAST

import struct

# SOCKET
SOCKET = socket(AF_INET, SOCK_DGRAM)
SOCKET.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
#SOCKET.setblocking(0)
BUFFERSIZE = 1280

# LOGGER
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


def log_response(socket):
    """Receive a response from socket and log it.

    Args:
        socket (socket.socket): The socket to receive from.
    Returns:
        --
    """
    message, address = socket.recvfrom(BUFFERSIZE)
    msg = message.decode('utf-8', 'ignore')
    logger.debug('Received %s from %s' % (msg, address))


def prepare_write(socket, address):
    """Send a begin-communication GCode to a printer.

    Args:
        socket (socket.socket): The socket to send to.
        address (tuple) A tuple of the printers ip and port.
    Returns:
        --
    """
    logger.info("Sending M4001")
    socket.sendto(b"M4001", address)  # SEND M4001 CODE TO PRINTER
    log_response(socket)


def begin_write(filename, socket, address):
    """Send a begin-file-write GCode to a printer.

    Args:
        filename (str): The file name to write to.
        socket (socket.socket): The socket to send to.
        address (tuple): A tuple of the printers ip and port.
    Returns:
        --
    """
    logger.info("Sending M28")
    cmd = 'M28 ' + filename  # SEND M28 CODE TO PRINTER
    socket.sendto(cmd.encode('utf-8', 'ignore'), address)
    log_response(socket)


def end_write(filename, socket, address):
    """Send a end-file-write GCode to a printer.

    Args:
        filename (str): The file name to write to.
        socket (socket.socket): The socket to send to.
        address (tuple): A tuple of the printers ip and port.
    Returns:
        --
    """
    logger.info("Sending M29")
    cmd = 'M29 ' + filename  # SEND M29 CODE TO PRINTER
    socket.sendto(cmd.encode('utf-8', 'ignore'), address)
    log_response(socket)


def send_file(filename, socket, address):
    """Send a file to a printer.

    Reads a file in buffer-sized chunks, transforms them into a sendable format
    and sends them to the printer.

    Args:
        filename (str): The name of the file to send.
        socket (socket.socket): The socket to send to.
        address (tuple): A tuple of the printers ip and port.
    Returns:
        --
    """
    logger.info("Sending file %s" % filename)

    # smaller/more readable getting of filesize
    filesize = os.path.getsize(filename)
    read_bytes = 0

    with open(filename, 'rb', buffering=1) as fp:
        while True:
            # get current position in file
            cur_file_pos = fp.tell()
            # and read a buffersize length chunk from it
            chunk = fp.read(BUFFERSIZE)
            if not chunk:
                logger.info('Chunk read from file is empty, were done.')
                break
            # try sending a chunk, log if it fails
            try:
                send_chunk(chunk, cur_file_pos, socket, address)
                # alternative progress implementation!
                # if len(chunk) is too imprecise, we can should let send_chunk
                # return the exact length and use that
                read_bytes += len(chunk)
                percentage = round(read_bytes / filesize * 100)
				
                print('progress: {n}%'.format(n=percentage))
            except ValueError as e:
                logger.warning('Encountered ValueError while sending chunk', e)
        # with blocks automatically close their file objects. :D
        # that means we need no fp.close()


def send_chunk(chunk, cur_file_pos, socket, address):
    """Send a chunk to a printer.

    Args:
        chunk: The data to be sent.
        cur_file_pos (int): Reading position in the current file.
        socket (socket.socket): The socket to send to.
        address (tuple): A tuple of the printers ip and port.
    Returns:
        --
    Raises:
        ValueError when chunk size is 0.
    """
    chunk_array = bytearray(chunk)  # Turn chunk into byte array
    chunk_size = len(chunk_array)  # And get its size

    # geki hunch: this shouldnt get executed because chunk being 0-length
    # should have been caught in send_file()s 'if not chunk'
    if chunk_size <= 0:
        raise ValueError('Chunk size <= 0 (%s)' % chunk_size)

    # making data_array can fail with a ValueError
    # well catch it in send_file
    data_array = make_checksum_array(chunk, cur_file_pos)

    socket.sendto(data_array, address)
    log_response(socket)


def make_checksum_array(data, cur_file_pos):
    """Transform data into a sendable format.

    Args:
        data: The data to be transformed.
        cur_file_pos (int): Reading position in the current file.
    Returns:
        A transformed bytearray chunk.
    Raises:
        ValueError when data size is 0.
    """
    data_array = bytearray(data + b'000000')
    data_size = len(data_array) - 6

    # geki hunch: this shouldnt get executed because we checked datas length
    # in send_chunk()
    if data_size <= 0:
        raise ValueError('Array construction failed:\
                Data size <= 0 (%s)' % data_size)

    # only construct seek_array if checksum doesnt terminate before
    # also, i have no idea what this line does XD and why it needs cur_file_pos
    seek_array = struct.pack('>I', cur_file_pos)

    # this seems to append the beginning 4 values at the end in reverse order
    data_array[data_size] = seek_array[3]
    data_array[data_size + 1] = seek_array[2]
    data_array[data_size + 2] = seek_array[1]
    data_array[data_size + 3] = seek_array[0]

    # construct checksum and put after the mirrored values
    # range(x) == range(0, x, 1)
    # also, i put the checksum initialising line to the loop that works on it
    checksum = 0
    for i in range(data_size+4):
        # short for checksum = checksum XOR data_array[i]
        checksum ^= data_array[i]
        data_array[data_size + 4] = checksum

    # this stays constant, thus i took it out of the checksum loop
    data_array[data_size + 5] = 0x83

    return data_array


def send_command(cmd, socket, address):
    """Send an arbitrary command to a printer.

    Args:
        cmd (str): The command to send.
        socket (socket.socket): The socket to send to.
        address (tuple): A tuple of the printers ip and port.
    Returns:
        --
    """
    # i replaced the manual sending of m4001 with a call to prepare_write
    prepare_write(socket, address)
    socket.sendto(cmd, address)  # SEND CMD CODE TO PRINTER
    log_response(socket)

if __name__ == '__main__':
    print("Welcome to FC3D (File & Command sender for 3D printers")
    print("----------------------------------------------------------")
    print("Current range of printers tested: ")
    print("X-smart, X-pro")
    print("----------------------------------------------------------")

    ip = raw_input("Please enter ip address: ")
    print("----------------------------------------------------------")

    port = raw_input("Please enter ip port: ")
    address = (ip, int(port))
    print("----------------------------------------------------------")

    option = raw_input("Do you want to send a file / command / or custom command: ")

    if option.lower() in ['file', 'f']:
        gcodefile = raw_input("Please enter path to file: ")
        print("----------------------------------------------------------")
        prepare_write(SOCKET, address)
        time.sleep(2)
        begin_write(gcodefile, SOCKET, address)
        time.sleep(2)
        send_file(gcodefile, SOCKET, address)
        time.sleep(2)
        end_write(gcodefile, SOCKET, address)

    if option.lower() in ['command', 'c']:
        print("----------------------------------------------------------")
        print("HOME Z")
        print("HOME X,Y")
        print("HOME ALL")
        print("DELETE FILE FROM SD")
        print("----------------------------------------------------------")

        command = raw_input("Please enter a listed command: ")

        # theres probably a way neater way of not having to duplicate the
        # send_command call in each if
        if command.lower() in ['home z', 'z']:
            print("HOMING Z")
            cmd = "G28 Z"
            send_command(cmd, SOCKET, address)
        elif command.lower() in ['home x,y', 'x']:
            print("HOMING X & Y")
            cmd = "G28 X Y"
            send_command(cmd, SOCKET, address)
        elif command.lower() in ['home all', 'a']:
            print("HOMING ALL")
            cmd = "G28"
            send_command(cmd, SOCKET, address)
        elif command.lower() in ['delete file from sd card', 'd']:
            gcodefile = raw_input("Please filename on sd card: ")
            cmd = "M30 " + gcodefile
            send_command(cmd, SOCKET, address)
        elif command.lower() in ['exit', 'e']:
            exit()
			
    if option.lower() in ['custom', 'cu']:
	customcommand = raw_input("Please enter command: ")
    cmd = customcommand
    send_command(cmd, SOCKET, address)
