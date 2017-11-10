import struct
def header (datagram) :
	received = struct.unpack('!BHBH'+str(len(datagram)-4)+'s', datagram) #unpack header in received[4] we have all other fields of th datagram
	return received	
