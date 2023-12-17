#!/usr/bin/env python3
import time
import logging
import os
import struct
from socket import socket, AF_INET, SOCK_DGRAM, SOL_SOCKET, SO_BROADCAST

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# Constants
BUFFERSIZE = 1280

# Initialize socket
SOCKET = socket(AF_INET, SOCK_DGRAM)
SOCKET.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)

def log_response(message, address):
    """Receive a response from a socket and log it.

    Args:
        message (bytes): The received message.
        address (tuple): The address from which the message was received.

    Returns:
        None
    """
    logger.debug(f"Received {message.decode('utf-8', 'ignore')} from {address}")

def send_command(cmd, socket, address):
    """Send an arbitrary command to a printer.

    Args:
        cmd (str): The command to send.
        socket (socket.socket): The socket to send to.
        address (tuple): A tuple of the printer's IP address and port.

    Returns:
        None
    """
    prepare_write(socket, address)
    socket.sendto(cmd.encode('utf-8', 'ignore'), address)
    log_response(cmd.encode('utf-8', 'ignore'), address)

def prepare_write(socket, address):
    """Send a begin-communication GCode to a printer.

    Args:
        socket (socket.socket): The socket to send to.
        address (tuple): A tuple of the printer's IP address and port.

    Returns:
        None
    """
    logger.info("Sending M4001")
    socket.sendto(b"M4001", address)
    log_response(b"M4001", address)

def begin_write(filename, socket, address):
    """Send a begin-file-write GCode to a printer.

    Args:
        filename (str): The name of the file to write to.
        socket (socket.socket): The socket to send to.
        address (tuple): A tuple of the printer's IP address and port.

    Returns:
        None
    """
    logger.info("Sending M28")
    cmd = f'M28 {filename}'
    socket.sendto(cmd.encode('utf-8', 'ignore'), address)
    log_response(cmd.encode('utf-8', 'ignore'), address)

def end_write(filename, socket, address):
    """Send an end-file-write GCode to a printer.

    Args:
        filename (str): The name of the file to write to.
        socket (socket.socket): The socket to send to.
        address (tuple): A tuple of the printer's IP address and port.

    Returns:
        None
    """
    logger.info("Sending M29")
    cmd = f'M29 {filename}'
    socket.sendto(cmd.encode('utf-8', 'ignore'), address)
    log_response(cmd.encode('utf-8', 'ignore'), address)

def send_file(filename, socket, address):
    """Send a file to a printer.

    Args:
        filename (str): The name of the file to send.
        socket (socket.socket): The socket to send to.
        address (tuple): A tuple of the printer's IP address and port.

    Returns:
        None
    """
    logger.info(f"Sending file {filename}")
    filesize = os.path.getsize(filename)
    read_bytes = 0

    with open(filename, 'rb', buffering=1) as fp:
        while True:
            cur_file_pos = fp.tell()
            chunk = fp.read(BUFFERSIZE)
            if not chunk:
                logger.info('Chunk read from file is empty, we are done.')
                break
            try:
                send_chunk(chunk, cur_file_pos, socket, address, filesize)
            except ValueError as e:
                logger.warning('Encountered ValueError while sending chunk', e)

def send_chunk(chunk, cur_file_pos, socket, address, filesize):
    """Send a chunk to a printer.

    Args:
        chunk: The data to be sent.
        cur_file_pos (int): Reading position in the current file.
        socket (socket.socket): The socket to send to.
        address (tuple): A tuple of the printer's IP address and port.
        filesize (int): Total size of the file being sent.

    Returns:
        None
    """
    chunk_array = bytearray(chunk)
    chunk_size = len(chunk_array)
    if chunk_size <= 0:
        raise ValueError(f'Chunk size <= 0 ({chunk_size})')

    data_array = make_checksum_array(chunk, cur_file_pos)
    socket.sendto(data_array, address)
    log_response(data_array, address)

def make_checksum_array(data, cur_file_pos):
    """Transform data into a sendable format.

    Args:
        data: The data to be transformed.
        cur_file_pos (int): Reading position in the current file.

    Returns:
        A transformed bytearray chunk.
    """
    data_array = bytearray(data + b'000000')
    data_size = len(data_array) - 6
    if data_size <= 0:
        raise ValueError(f'Array construction failed: Data size <= 0 ({data_size})')

    seek_array = struct.pack('>I', cur_file_pos)
    data_array[data_size:data_size+4] = seek_array[::-1]

    checksum = 0
    for i in range(data_size + 4):
        checksum ^= data_array[i]
        data_array[data_size + 4] = checksum

    data_array[data_size + 5] = 0x83
    return data_array

if __name__ == '__main__':
    print("Welcome to FC3D (File & Command sender for 3D printers")
    print("----------------------------------------------------------")
    print("Current range of printers tested: ")
    print("X-smart, X-pro")
    print("----------------------------------------------------------")

    ip = input("Please enter IP address: ")
    port = input("Please enter IP port: ")
    address = (ip, int(port))

    option = input("Do you want to send a file / command / or custom command: ")

    if option.lower() in ['file', 'f']:
        gcodefile = input("Please enter path to file: ")
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

        command = input("Please enter a listed command: ")

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
            gcodefile = input("Please filename on SD card: ")
            cmd = f"M30 {gcodefile}"
            send_command(cmd, SOCKET, address)
        elif command.lower() in ['exit', 'e']:
            exit()

    if option.lower() in ['custom', 'cu']:
        customcommand = input("Please enter command: ")
        cmd = customcommand
        send_command(cmd, SOCKET, address)
