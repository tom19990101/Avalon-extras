#!/usr/bin/env python2.7

# This simple script was for test A3255 modular. there are 128 cores in one A3255 chip.
# If all cores are working the number should be 0.
# If some of them not working the number is the broken cores count.
# Note: Avalon 3.5 use usb2iic instead of uart, the usb2iic bridge expose hid api to app.
# Depends : PyUSB 1.0 (Under Linux)
# PyUSB 1.0 Installation: https://github.com/walac/pyusb
#
#  bridge format: length[1]+transId[1]+sesId[1]+req[1]+data[60]
#  length: 4+len(data)
#  transId: 0
#  sesId: 0
#  req:
#        0:RESET
#        1:INIT
#        2:DEINIT
#        3:WRITE
#        4:READ
#        5:XFER
#  data: the actual payload
#        clockRate[4] + reserved[4] + payload[52] when init
#        xparam[4] + payload[56] when write
#            xparam: txSz[1]+rxSz[1]+options[1]+slaveAddr[1]
#        payload[60] when read
#

import sys
import binascii
import time
from serial import Serial
from optparse import OptionParser
from array import array

parser = OptionParser()
parser.add_option("-s", "--serial", dest="serial_port", default="/dev/ttyACM0", help="Serial port")
parser.add_option("-m", "--module", dest="module_id", default="0", help="Module ID: 0 - 3, default:0")
parser.add_option("-M", "--Mode", dest="run_mode", default="0", help="Run Mode:0-Normal,1-Loopback test; default:0")
parser.add_option("-S", "--static", dest="is_static", default="0", help="Static flag: 0-turn off, 1-turn on")
(options, args) = parser.parse_args()

asic_cnt = 10
miner_cnt = 5
ser = Serial(options.serial_port, 115200, 8, timeout=0.02)

# addr : iic slaveaddr
# req : see bridge format
# data: 40 bytes payload
def cdc_req(addr, req, data):
    req = req.rjust(2, '0')

    if req == 'a1':
        data = data.ljust(120, '0')
        datalen = 12
        txdat = hex(datalen)[2:].rjust(2, '0') + \
                "0000" +    \
                req +   \
                data
        ser.write(txdat.decode("hex"))

    if req == 'a3' or req == 'a5':
        data = data.ljust(112, '0')
        datalen = 8 + len(data)
        txdat = hex(datalen)[2:].rjust(2, '0') +    \
                "0000" +    \
                "a5" + \
                "280000" +  \
                addr.rjust(2, '0') +    \
                data
        ser.write(txdat.decode("hex"))
        ser.read(64)

    if req == 'a4' or req == 'a5':
        datalen = 8
        txdat = hex(datalen)[2:].rjust(2, '0') +    \
                "0000" +    \
                "a5" + \
                "002800" +  \
                addr.rjust(2, '0') +    \
                "0".ljust(112, '0')
        ser.write(txdat.decode("hex"))

def cdc_read():
    mylist = []
    ret = ser.read(64)

    if isinstance(ret, str):
        for c in ret:
            mylist.append(ord(c))
        del(ret)
        ret = array("B", mylist)

    if ret and ret[0] > 4:
        return ret[4:ret[0]]
    else:
        return None

def cdc_xfer(addr, req, data):
    cdc_req(addr, req, data)
    return cdc_read()

def run_loopback():
    # addressing 0x18
    ret = cdc_xfer("00", "a5", "0000000000000018")
    if ret:
        rxdat = binascii.hexlify(ret)
        print "DNA = " + rxdat[:16]
    else:
        print "Read DNA Failed!"

    # loopback on 0x18
    txdat = "000000011234567890123456789012345678901234567890123456789012345678901234567890"
    for i in range(1, 4):
        ret = cdc_xfer("18", "a5", txdat +  str(i).rjust(2,'0'))
        if ret:
            rxdat = binascii.hexlify(ret)
            if rxdat == (txdat +  str(i).rjust(2,'0')):
                print "Loopback success" + str(i)
            else:
                print "txdat = " + txdat
                print "rxdat = " + rxdat
                print "Loopback failed"

        else:
            print "Read None"

TYPE_TEST = "14"
TYPE_DETECT = "0a"
TYPE_REQUIRE = "12"

def CRC16(message):
	#CRC-16-CITT poly, the CRC sheme used by ymodem protocol
	poly = 0x1021
	 #16bit operation register, initialized to zeros
	reg = 0x0000
	#pad the end of the message with the size of the poly
	message += '\x00\x00'
	#for each bit in the message
	for byte in message:
		mask = 0x80
		while(mask > 0):
			#left shift by one
			reg<<=1
			#input the next bit from the message into the right hand side of the op reg
			if ord(byte) & mask:
				reg += 1
			mask>>=1
			#if a one popped out the left of the reg, xor reg w/poly
			if reg > 0xffff:
				#eliminate any one that popped out the left
				reg &= 0xffff
				#xor with the poly, this is the remainder
				reg ^= poly
	return reg

def mm_package(cmd_type, module_id):
	data = "000000000000000000000000000000000000000000000000000000000000" + module_id.rjust(4, '0')
	crc = CRC16(data.decode("hex"))
	return "4156" + cmd_type + "0101" + data + hex(crc)[2:].rjust(4, '0')

def run_test(cmd):
        cdc_req("00", "a3", cmd)
	for count in range(0, miner_cnt):
                while True:
                    cdc_req("00", "a4", cmd)
                    res_s = cdc_read()
                    if res_s != None:
                        break

		if not res_s:
			print(str(count) + ": Something is wrong or modular id not correct")
		else :
			result = binascii.hexlify(res_s)
			for i in range(0, asic_cnt+1):
				number = '{:03}'.format(int(result[10 + i * 2:12 + i * 2], 16))
				if (i == 0):
					sys.stdout.write(number + ":\t")
				else :
					sys.stdout.write(number + "\t")
				sys.stdout.flush()
			print("")


def run_detect(cmd):
	#version
        res_s = cdc_xfer("00", "a5", cmd)
	if not res_s:
		print("ver:Something is wrong or modular id not correct")
	else :
		print("ver:" + ''.join([chr(x) for x in res_s])[3:20])

def run_require(cmd):
        res_s = cdc_xfer("00", "a5", cmd)
	if not res_s:
		print("status:Something is wrong or modular id not correct")
	else :
		# format: temp(40|50), fan(20|30), freq(300), vol(400), localwork(1), g_hw_work(300), pg(0)
		avalon_require = binascii.hexlify(res_s)
		temp1 = int(avalon_require[10:14], 16)
		temp2 = int(avalon_require[14:18], 16)
		fan1 = int(avalon_require[18:22], 16)
		fan2 = int(avalon_require[22:26], 16)
		freq = int(avalon_require[26:34], 16)
		vol = int(avalon_require[34:42], 16)
		localwork = int(avalon_require[42:50], 16)
		g_hw_work = int(avalon_require[50:58], 16)
		pg = int(avalon_require[58:66], 16)
		result = "status:temp(" + str(temp1) + "," + str(temp2) + "), "
		result = result + "fan1(" + str(fan1) + "," + str(fan2) + "), "
		result = result + "freq(" + str(freq) + "), "
		result = result + "vol(" + str(vol) + "), "
		result = result + "localwork(" + str(localwork) + "), "
		result = result + "g_hw_work(" + str(g_hw_work) + "), "
		result = result + "pg(" + str(pg) + ")"
		print(result)

def statics():
    start = time.time()
    for i in range(0, 1000):
        run_detect(mm_package(TYPE_DETECT, options.module_id))
    print "time elapsed: %s" %(time.time() - start)

def run_modular_test():
    while True:
        print("Reading result ...")
        print("module id:" + options.module_id)
        run_detect(mm_package(TYPE_DETECT, options.module_id))
        run_require(mm_package(TYPE_REQUIRE, options.module_id))
        run_test(mm_package(TYPE_TEST, options.module_id))
        raw_input('Press enter to continue:')

if __name__ == '__main__':
    ret = cdc_xfer("00", "a1", "40420f00")
    if ret:
        print "USB2IIC version: " +  ''.join([chr(x) for x in ret])
    else:
        print "USB2IIC version null"

    if options.is_static == '1':
        statics()
    else:
        if options.run_mode == '0':
            run_modular_test()
        else:
            run_loopback()
