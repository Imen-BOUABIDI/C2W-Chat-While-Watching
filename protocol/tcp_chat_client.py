# -*- coding: utf-8 -*-
from twisted.internet.protocol import Protocol
import logging
import struct
from twisted.internet import reactor
import math
from math import pow
import c2w
from c2w.main.constants import ROOM_IDS
from c2w.main.client_model import c2wClientModel
logging.basicConfig()
moduleLogger = logging.getLogger('c2w.protocol.tcp_chat_client_protocol')


class c2wTcpChatClientProtocol(Protocol):

	def __init__(self, clientProxy, serverAddress, serverPort):
		"""
		:param clientProxy: The clientProxy, which the protocol must use
			to interact with the Graphical User Interface.
		:param serverAddress: The IP address (or the name) of the c2w server,
			given by the user.
		:param serverPort: The port number used by the c2w server,
			given by the user.

		Class implementing the UDP version of the client protocol.

		.. note::
			You must write the implementation of this class.

		Each instance must have at least the following attribute:

		.. attribute:: clientProxy

			The clientProxy, which the protocol must use
			to interact with the Graphical User Interface.

		.. attribute:: serverAddress

			The IP address of the c2w server.

		.. attribute:: serverPort

			The port number used by the c2w server.

		.. note::
			You must add attributes and methods to this class in order
			to have a working and complete implementation of the c2w
			protocol.
		"""

		#: The IP address of the c2w server.
		self.serverAddress = serverAddress
		#: The port number used by the c2w server.
		self.serverPort = serverPort
		#: The clientProxy, which the protocol must use
		#: to interact with the Graphical User Interface.
		self.clientProxy = clientProxy
		self.c2wClientModel = c2wClientModel()
		self.last_event_id =0
		self.seq = 0
		self.userID = 0
		self.roomID = 0
		self.dstRoomID = 0
		self.init = False
		self.messageType = 0x00
		self.movieList = []
		self.userList = []
		self.connected = True
		self.responses = []
		self.lastDGTreated = None
		self.buf = bytearray()
		self.lenBuf = 0
		self.logged = False


	def incrementSeq(self) :
		if (self.seq > 65535) :
			self.seq = 0
		else :
			self.seq += 1

	#GET_PING send a message to the server asking for the last event of the room where the user is
	def getPing(self, initial):
		self.messageType = 0x4
		msgLength = 4
		buf = bytearray(10)
		last_event_id_2fb = (self.last_event_id & int('111111111111111100000000',2)) >> 8 #retrieve two first bytes in event_id
		last_event_id_lb = (self.last_event_id) & 255 #retrieve last byte in event_id
		struct.pack_into('!BHBHHBB', buf, 0, self.messageType, self.seq, self.userID, msgLength, last_event_id_2fb, last_event_id_lb, self.roomID)
		
		if self.logged == True :
			self.transport.write(buf)
			seq = self.seq
			msgType = self.messageType
			self.incrementSeq()
			reactor.callLater(0.5, self.verifyResponse, buf, seq, msgType) # if we don't receive response after 500ms, the GET_PING request is resent
			if initial == True:
				reactor.callLater(1, self.getPing, True)# this method is called every second, True means it's not a message retry, so it can call a new get ping after a second
			else:
				pass
		else :
			pass
	
	#split in groups of 254 the number of events to be asked to the server
	def getEvents(self, numberOfEvents): 
		nbIterations = math.ceil(numberOfEvents/254) #we calculate the number of times it will be necessary to ask for events eg: 300/254 = 1.18 -> 2 times 
		while(nbIterations != 0):
			if(numberOfEvents/254 >= 1):
				nbDemande = 254
				numberOfEvents -= 254
			else:
				nbDemande = numberOfEvents
			self.events(nbDemande)
			nbIterations -= 1
	
	#pack and send to the server the GET_EVENTS request
	def events(self, nbDemande) :
		self.messageType = 0x6
		msgLength = 5
		buf = bytearray(11)
		last_event_id_2fb = (self.last_event_id & int('111111111111111100000000',2)) >> 8
		last_event_id_lb = (self.last_event_id) & 255
		struct.pack_into('!BHBHHBBB', buf, 0, self.messageType, self.seq, self.userID, msgLength, last_event_id_2fb, last_event_id_lb, nbDemande, self.roomID)
		self.transport.write(buf)
		seq = self.seq
		msgType = self.messageType
		self.incrementSeq()
		reactor.callLater(0.5, self.verifyResponse, nbDemande, seq, msgType) #after a half second, we call a function that checks if the response was received 
	
	#PUT_LOGIN send a message to the server to inform it of the user's wish to enter the server	
	def sendLoginRequestOIE(self, userName):
		"""
		:param string userName: The user name that the user has typed.

		The client proxy calls this function when the user clicks on
		the login button.
		"""
		moduleLogger.debug('loginRequest called with username=%s', userName)
		self.messageType = 0x00
		usernameLength = len(userName.encode('utf-8')) #len returns the number of characters 
		msgLength = usernameLength + 1 # 1 for UL field
		buf = bytearray(7+usernameLength) #2 bytes for seq, 1 for userID,...
		struct.pack_into('!BHBHB'+str(usernameLength)+'s', buf, 0, self.messageType, self.seq, self.userID, msgLength, usernameLength, userName.encode('utf-8')) 
		self.transport.write(buf)
		seq = self.seq
		msgType = self.messageType
		self.incrementSeq()
		reactor.callLater(0.5, self.verifyResponse, userName, seq, msgType) #after a half second, we call a function that checks if the response was received

	#PUT_NEW_MESSAGE send a message to the server with the text the user has typed in the chatroom wether it is in the MAIN_ROOM or a MOVIE_ROOM
	def sendChatMessageOIE(self, message):
		"""
		:param message: The text of the chat message.
		:type message: string

		Called by the client proxy when the user has decided to send
		a chat message

		.. note::
		   This is the only function handling chat messages, irrespective
		   of the room where the user is.  Therefore it is up to the
		   c2wChatClientProctocol or to the server to make sure that this
		   message is handled properly, i.e., it is shown only by the
		   client(s) who are in the same room.
		"""
		self.messageType = 0x0E
		msgLength = 1 + 2 + len(message) #1 byte for room_id, 2 for text length...
		buf = bytearray(9+len(message)) #2 bytes for seq, 1 pour userID,...
		struct.pack_into('!BHBHBH'+str(len(message))+'s', buf, 0, self.messageType, self.seq, self.userID, msgLength, self.roomID, len(message), message.encode('utf-8'))
																																			 #the result is saved in buf
		self.transport.write(buf)
		seq = self.seq
		msgType = self.messageType
		self.incrementSeq()
		reactor.callLater(0.5, self.verifyResponse, message, seq, msgType) #after a half second, we call a function that checks if the response was received
	
	#PUT_SWITCH_ROOM send a message to the server to inform it of the user's wish to change rooms
	def sendJoinRoomRequestOIE(self, roomName):
		"""
		:param roomName: The room name (or movie title.)

		Called by the client proxy  when the user
		has clicked on the watch button or the leave button,
		indicating that she/he wants to change room.

		.. warning:
			The controller sets roomName to
			ROOM_IDS.MAIN_ROOM when the user
			wants to go back to the main room.
		"""
		if (roomName == ROOM_IDS.MAIN_ROOM) :
			self.dstRoomID = 0
		else :
			room = self.c2wClientModel.getMovieByTitle(roomName) 
			self.dstRoomID = room.movieId
		self.messageType = 0x0C
		msgLength = 1 #1 for ROOM_ID
		buf = bytearray(7)
		struct.pack_into('!BHBHB', buf, 0, self.messageType, self.seq, self.userID, msgLength, self.dstRoomID)
		self.transport.write(buf)
		seq = self.seq
		msgType = self.messageType
		self.incrementSeq()
		reactor.callLater(0.5, self.verifyResponse, roomName, seq, msgType) #after a half second, we call a function that checks if the response was received

	#PUT_LOGOUT send a message to the server to inform it of the user's wish to leave the server
	def sendLeaveSystemRequestOIE(self):
		"""
		Called by the client proxy  when the user
		has clicked on the leave button in the main room.
		"""
		self.messageType = 0x02
		msgLength = 0
		buf = bytearray(6) 
		struct.pack_into('!BHBH', buf, 0, self.messageType, self.seq, self.userID, msgLength)
		self.transport.write(buf)
		seq = self.seq
		msgType = self.messageType
		self.incrementSeq()
		reactor.callLater(0.5, self.verifyResponse, buf, seq, msgType) #after a half second, we call a function that checks if the response was received

	# GET_ROOMS send a message to the server to ask for the list of movies	
	def getRooms(self) :
		self.messageType = 0x08
		msgLength = 2 #1 for FIRST_ROOM_ID 1 for NBR_ROOMS
		buf = bytearray(8) 
		struct.pack_into('!BHBHBB', buf, 0, self.messageType, self.seq, self.userID, msgLength, 1, 255)
		self.transport.write(buf)
		seq = self.seq
		msgType = self.messageType
		self.incrementSeq()
		reactor.callLater(0.5, self.verifyResponse, buf, seq, msgType) #after a half second, we call a function that checks if the response was received
	
	#GET_USERS send a message to the user to ask for the list of users in the server (MAIN_ROOM) or in the room (MOVIE_ROOM)
	def getUsers(self, roomID) :
		self.messageType = 0x0A
		msgLength = 3 
		buf = bytearray(9) 
		struct.pack_into('!BHBHBBB', buf, 0, self.messageType, self.seq, self.userID, msgLength, 1, 255, self.roomID)
		self.transport.write(buf)
		seq = self.seq
		msgType = self.messageType
		self.incrementSeq()
		reactor.callLater(0.5, self.verifyResponse, roomID, seq, msgType) #after a half second, we call a function that checks if the response was received
	
	#unpack the RESPONSE_USERS datagram and return the list of users received (userName, userRoom)
	def unpackUsersList(self, datagram) :
		usersPack = struct.unpack('!BHBHB'+str(len(datagram)-7)+'s', datagram)
		nbUsers = usersPack[4]
		users = usersPack[5] #USERS list (variable length)
		listUsers = users
		userTuples=[]
		while (nbUsers != 0) :
			user1 = struct.unpack('!BB'+str(len(listUsers)-2)+'s', listUsers) #separate USER_ID, UL and the rest
			user11 = struct.unpack('!'+str(user1[1])+'sB'+str(len(user1[2])-user1[1]-1)+'s', user1[2]) #separate USERNAME, ROOM_ID and the rest
			userID = user1[0]
			userName = user11[0].decode('utf-8')
			roomID = user11[1]
			if (roomID == 0) :
				userRoom = ROOM_IDS.MAIN_ROOM
				movieName = userRoom
			else :
				userRoom = ROOM_IDS.MOVIE_ROOM
				if self.init == True : #for loggin initialisation, we just need to know if the user is in the main room or in the movie room
					movieName = userRoom
				else :
					movie = self.c2wClientModel.getMovieById(roomID)
					movieName = movie.movieTitle
			userTuples.append((userName, userRoom)) #add USERNAME and ROOM_ID to the list of pair
			user=self.c2wClientModel.getUserByName(userName)
			if user != None :
				pass
			else :
				self.c2wClientModel.addUser(userName, userID, movieName) #store user informations
			nbUsers-=1
			listUsers = user11[2] #make the initial packet equal to the rest, in order to retrieve the other users through further iterations
			self.c2wClientModel.updateUserChatroom(userName, userRoom)
			if (self.init == False) : 
				self.clientProxy.userUpdateReceivedONE(userName, movieName) #won't be execute for the initial response user
			else :
				pass
		return userTuples
	
	#unpack the RESPONSE_ROOMS datagram and return the list of movies received (movieTitle, movieIP, moviePort)
	def unpackRoomsList(self, datagram) :
		moviesPack = struct.unpack('!BHBHB'+str(len(datagram)-7)+'s', datagram)
		nbMovies = moviesPack[4]
		movies = moviesPack[5]
		listMovies = movies	
		moviesTriplets=[]
		while (nbMovies != 0) :
			movie1 = struct.unpack('!B4BHB'+str(len(listMovies)-8)+'s', listMovies) #separate ROOM_ID, IP, PORT_NUMBER, RNL and the rest
			movieID = movie1[0]
			moviePort = movie1[5]
			movieIP = str(movie1[1])+"."+str(movie1[2])+"."+str(movie1[3])+"."+str(movie1[4])
			movie11 = struct.unpack('!'+str(movie1[6])+'sB'+str(len(movie1[7])-movie1[6]-1)+'s', movie1[7]) #separate ROOM_NAME, NBR_USERS and the rest
			movieTitle = movie11[0].decode('utf-8')
			moviesTriplets.append((movieTitle, movieIP, moviePort)) #add ROOM_NAME, IP and PORT_NUMBER to the list of triplets
			self.c2wClientModel.addMovie(movieTitle, movieIP, moviePort, movieID) #store movie informations
			nbMovies-=1
			listMovies = movie11[2] #make the initial packet equal to the rest, in order to retrieve the other videos through further iterations
		print (moviesTriplets)
		return moviesTriplets
	
	#unpack the RESPONSE_EVENTS datagram and execute the necessary updates
	def unpackEvents(self, datagram) :
		eventsPack = struct.unpack('!BHBHB'+str(len(datagram)-7)+'s', datagram) #separate MESSAGE_TYPE, SEQ_NUMBER, USER_ID, MESSAGE_LENGTH (header), NBR_EVENTS and the events
		nbEvents = eventsPack[4]
		events = eventsPack[5]
		while(nbEvents != 0) :
			event1 = struct.unpack('!HBBBB'+str(len(events)-6)+'s', events) #separate EVENT_ID, EVENT_TYPE, ROOM_ID, USER_ID, and the rest
			self.last_event_id = (event1[0]<<8)|event1[1]
			roomID = event1[3]
			userID = event1[4]
			eventType = event1[2]
			
			#MESSAGE event: MESSAGE_LENGTH, MESSAGE
			if (eventType==0x1) :
				event11 = struct.unpack('!H'+str(len(event1[5])-2)+'s', event1[5]) #separate MESSAGE_LENGTH (chat) and the rest
				event111 = struct.unpack('!'+str(event11[0])+'s'+str(len(event11[1])-event11[0])+'s', event11[1]) #separate MESSAGE and the rest
				message = event111[0].decode('utf-8')
				user = self.c2wClientModel.getUserById(userID) #retrieve the user using USER_ID
				userName = user.userName
				if userID != self.userID and self.roomID == roomID : #print the msg only if the message is from another user in the same room. (care of duplication)
					self.clientProxy.chatMessageReceivedONE(userName, message)
				else :
					pass
				events = event111[1]
				
			#NEW_USER event: USERNAME_LENGTH, USERNAME
			elif (eventType==0x2) :
				event11 = struct.unpack('!B'+str(len(event1[5])-1)+'s', event1[5]) #separate UL and the rest
				event111 = struct.unpack('!'+str(event11[0])+'s'+str(len(event11[1])-event11[0])+'s', event11[1]) #separate USERNAME and the rest
				if (roomID == 0) :
					userRoom = ROOM_IDS.MAIN_ROOM
					movieName= userRoom
				else :
					userRoom = ROOM_IDS.MOVIE_ROOM
					movie = self.c2wClientModel.getMovieById(roomID)
					movieName = movie.movieTitle
				userName = event111[0].decode('utf-8')
				user=self.c2wClientModel.getUserByName(userName)
				if user != None : #prevent to add user if he exists, because we add user after response user.
					pass
				else :
					self.c2wClientModel.addUser(userName, userID, movieName) #store user informations
				self.c2wClientModel.updateUserChatroom(userName, userRoom)
				self.clientProxy.userUpdateReceivedONE(userName, movieName)
				events = event111[1]
			
			#SWITCH_ROOM event: NEW_ROOM_ID
			elif (eventType==0x3) :
				event11 = struct.unpack('!B'+str(len(event1[5])-1)+'s', event1[5]) #separate NEW_ROOM_ID and the rest
				newRoomID = event11[0]
				if (newRoomID == 0) :
					room = ROOM_IDS.MAIN_ROOM
					movieName = room
				else :
					room = ROOM_IDS.MOVIE_ROOM
					movie = self.c2wClientModel.getMovieById(newRoomID)
					movieName = movie.movieTitle
				user = self.c2wClientModel.getUserById(userID) #retrieve the user using USER_ID	
				userName = user.userName
				self.c2wClientModel.updateUserChatroom(userName, room)
				self.clientProxy.userUpdateReceivedONE(userName, movieName)
				events = event11[1]
			
			#LOGOUT event:
			elif (eventType==0x4) :
				user = self.c2wClientModel.getUserById(userID) #retrieve the user using USER_ID
				userName = user.userName
				self.clientProxy.userUpdateReceivedONE(userName, ROOM_IDS.OUT_OF_THE_SYSTEM_ROOM)
				self.c2wClientModel.removeUser(userName)
				events = event1[5]
			else :
				pass
			nbEvents-=1
			
	def leaveApplication(self):
		self.clientProxy.connectionRejectedONE("Connexion lost")
		reactor.callLater(2, self.clientProxy.applicationQuit)
		self.logged = False

	#identify the response message type and execute the necessary actions
	def treatDatagram(self, datagram) :
		received = struct.unpack('!BH'+str(len(datagram)-3)+'s', datagram)
		msgType = received[0]

		#RESPONSE_LOGIN
		if (msgType == 0x01) :
			received = struct.unpack('!BHBHBBHB', datagram) #unpack the received data
			status_code = received[4]
			#successful login
			if (status_code==0x00) :
				self.init = True
				self.logged = True
				self.last_event_id = (received[6]<<8)|received[7] #shift the 2 first bytes of the last_event_id to the left and apply a bitwise OR with the last byte
				self.userID = received[5]
				self.getUsers(self.roomID)
				self.connectedTimer = reactor.callLater(60, self.leaveApplication) #if no data received every 60s, we conclude that the connexion is lost
																					# connectedTimer is reinitialised after each data reception
			#unsuccessful login
			elif (status_code==0x01) :
				self.clientProxy.connectionRejectedONE("unknown error")
			elif (status_code==0x02) :
				self.clientProxy.connectionRejectedONE("too many users")
			elif (status_code==0x03) :
				self.clientProxy.connectionRejectedONE("invalid username")
			elif (status_code==0x04) :
				self.clientProxy.connectionRejectedONE("username not available")
			else :
				self.clientProxy.connectionRejectedONE("error")
			
		#RESPONSE_LOGOUT
		elif (msgType == 0x03) :
			received = struct.unpack('!BHBHB', datagram) #unpack the received data
			status_code = received[4]
			if (status_code == 0) :
				self.clientProxy.leaveSystemOKONE()
				self.logged = False
				self.connectedTimer.cancel() #stop timmer
			else :	
				pass
			
		#RESPONSE_PING get the difference betwen server's and user's last event id's
		elif (msgType == 0x05) :
			received = struct.unpack('!BHBHHB', datagram) #unpack the received data containing last event id
			last_event_id = (received[4]<<8)|received[5] 
			if (last_event_id>self.last_event_id): #if server last_event_id is greater than the client
				diff = last_event_id - self.last_event_id
				self.getEvents(diff) #client asks for the remaining events
			elif (last_event_id<self.last_event_id): #if client last_event_id is greater than the server's, it means the server has reached the max seq and then reinitialised it
				diff = last_event_id + (math.pow(2,24) - self.last_event_id) #(math.pow(2,24) - self.last_event_id) : events that took place in the server before reinitialisation
				self.getEvents(diff) #client asks for the events before and after seq reinitialisation
			else:
				pass
			
		#RESPONSE_EVENTS
		elif (msgType == 0x07) :
			self.unpackEvents(datagram)
			
		#RESPONSE_USERS
		elif (msgType == 0x0B) :			
			self.userList = self.unpackUsersList(datagram) #get the list of users in the list of pairs format (USERNAME, ROOM_ID)
			if self.init == True : #self.init set to True when successful loggin and to false when we got response rooms. we call getRooms after response user only for loggin 
				self.getRooms()
			else :
				pass

			
		#RESPONSE_ROOMS
		elif (msgType == 0x09) :
			self.movieList = self.unpackRoomsList(datagram) #get the list of triplets with movies' info	
			self.clientProxy.initCompleteONE(self.userList, self.movieList) #when init is true, it means we have just logged in, and so initialisation is complete
			reactor.callLater(1, self.getPing, True) #call getPing 1s after complete login
			self.init = False


		#RESPONSE_SWITCH_ROOM
		elif (msgType == 0x0D) :
			received = struct.unpack('!BHBHB', datagram) #unpack the received data
			status_code = received[4]
			if (status_code==0x0) :
				self.roomID = self.dstRoomID
				self.getUsers(self.roomID)
				user = self.c2wClientModel.getUserById(self.userID)
				userName = user.userName
				if (self.roomID == 0) :
					userRoom = ROOM_IDS.MAIN_ROOM
					movieName = userRoom
				else :
					userRoom = ROOM_IDS.MOVIE_ROOM
					movie = self.c2wClientModel.getMovieById(self.roomID)
					movieName = movie.movieTitle
				self.c2wClientModel.updateUserChatroom(userName, userRoom)
				self.clientProxy.userUpdateReceivedONE(userName, movieName)
				self.clientProxy.joinRoomOKONE()
			else :
				pass

		#RESPONSE_NEW_MESSAGE
		elif (msgType == 0x0F) :
			received = struct.unpack('!BHBHB', datagram) #unpack the received data
			status_code = received[4]
			if (status_code==0x0) :
				pass
			else :
				pass

		else:
			pass

	def analyseSequence(self, datagram) :
		received = struct.unpack('!BH'+str(len(datagram)-3)+'s', datagram)
		msgType = received[0]
		seq = received[1]
		#the case in which we receive the login message (it's always the first message, so we can execute it whitout checking if there are others with an inferior sequence number)
		if self.lastDGTreated == None and seq == 0 :
			self.treatDatagram(datagram)
			self.lastDGTreated = 0
		#the case in which the message is the expected, we can execute it without worries, and after that we check the list of responses received for ensuing messages
		elif seq == self.lastDGTreated + 1 :
			self.treatDatagram(datagram)
			self.lastDGTreated = self.lastDGTreated + 1
			quit = False
			while quit == False : 
				i = 0
				quit = True
				for item in self.responses :
					if (item[1] == self.lastDGTreated + 1):
						self.treatDatagram(item[2])
						self.lastDGTreated = self.lastDGTreated + 1
						del self.responses[i] #remove the treated data in self.responses
						quit = False
						break
					else :
						i += 1
		#the case in which there's a gap in the sequence number, it means that one or more packets weren't received. We store the datagram in a list 
		elif seq > self.lastDGTreated + 1 :
			self.responses.append((msgType, seq, datagram))
		else :
			pass

	def dataReceived(self, data):
		"""
		:param data: The data received from the client (not necessarily
					 an entire message!)

		Twisted calls this method whenever new data is received on this
		connection.
		"""
		if self.logged == True : # when a datagram is received we reset the connectedTimer to 0
			self.connectedTimer.reset(60)
		else :
			pass
		self.buf = self.buf + data #add received data to the buf
		self.lenBuf = len(self.buf)
		if (self.lenBuf > 6) : #if len buf is greater than 6 (header) it means we can treat the data, otherwise we wait
			received = struct.unpack('!BHBH'+str(len(self.buf)-6)+'s', self.buf)
			expectedMsgLength = received[3] # we use the field message_length to know if we got the whole msg
			receivedMsgLength = len(received[4])
			while receivedMsgLength >= expectedMsgLength and len(self.buf)>6 : #if the received msg is bigger than expected, it means we already received a part of another msg
				received = struct.unpack('!BHBH'+str(len(self.buf)-6)+'s', self.buf)
				expectedMsgLength = received[3]
				receivedMsgLength = len(received[4])
				if (receivedMsgLength < expectedMsgLength) :
					pass
				elif (receivedMsgLength == expectedMsgLength) : #we receive the expected msg length, we can treat the data
					self.analyseSequence(self.buf)
					self.buf = bytearray()
				else:
					received1 = struct.unpack('!'+str(6+expectedMsgLength)+'s'+str(self.lenBuf-6-expectedMsgLength)+'s', self.buf) #separate the exepected data and put the rest
																																	#in buf
					expectedData = received1[0]
					self.analyseSequence(expectedData)
					self.buf = received1[1] 
		else :
			pass

	#check if the response was received, called in general 500ms after sending the message
	def verifyResponse(self, parameter, respSeq, messageType): #respSeq is used to be sure that the received response is the expected 
		#the case in which the lastDGTreated is still uninitialized, that means the login response wasn't received. We then resend the request
		if respSeq == 0 and self.lastDGTreated == None :
			self.seq -= 1
			self.sendLoginRequestOIE(parameter)
		#the case in which the lastDGTreated already surpassed the seq number we are checking. It means the datagram was already received and executed, so we don't have to do anything
		elif respSeq <= self.lastDGTreated :
			return
		#the case in which the lastDGTreated is inferior to the seq number we are checking. It means the datagram wasn't executed yet, so we have to search it in the list
		elif respSeq > self.lastDGTreated :
			i = 0
			for item in self.responses :
				#the case in which the response datagram was already received, but wasn't executed, we have to wait for the messages with an inferior seq number to be executed 
				if (item[1] == respSeq):
					return
				else :
					i += 1
			#the case in which the response datagram wasn't received yet (it's not in the list), we have to resend the request 
			tempSeq = self.seq
			self.seq = respSeq #if we didn't receive the expected seq response, we resend the request with the expected seq (respSeq)
			print(self.seq)
			if(messageType == 0x02):
				self.sendLeaveSystemRequestOIE()
			elif(messageType == 0x04):
				self.getPing(False) #false parameter means it is a retry, so we don't call a new get ping after a second
			elif(messageType == 0x06):
				self.getEvents(parameter)
			elif(messageType == 0x08):
				self.getRooms()
			elif(messageType == 0x0A):
				self.getUsers(self.roomID)
			elif(messageType == 0x0C):
				self.sendJoinRoomRequestOIE(parameter)
			elif(messageType == 0x0E):
				self.sendChatMessageOIE(parameter)
			else:
				pass
			self.seq = tempSeq #continue the code with our current seq
		else :
			pass
