# -*- coding: utf-8 -*-
from twisted.internet.protocol import DatagramProtocol
from c2w.main.lossy_transport import LossyTransport
import logging
import struct
import sys
import c2w
from twisted.internet import reactor
from c2w.main.constants import ROOM_IDS
logging.basicConfig()
moduleLogger = logging.getLogger('c2w.protocol.udp_chat_server_protocol')


class c2wUdpChatServerProtocol(DatagramProtocol):

    def __init__(self, serverProxy, lossPr):
        """ 
        :param serverProxy: The serverProxy, which the protocol must use
            to interact with the user and movie store (i.e., the list of users
            and movies) in the server.
        :param lossPr: The packet loss probability for outgoing packets.  Do
            not modify this value!

        Class implementing the UDP version of the client protocol.

        .. note::
            You must write the implementation of this class.

        Each instance must have at least the following attribute:

        .. attribute:: serverProxy

            The serverProxy, which the protocol must use
            to interact with the user and movie store in the server.

        .. attribute:: lossPr

            The packet loss probability for outgoing packets.  Do
            not modify this value!  (It is used by startProtocol.)

        .. note::
            You must add attributes and methods to this class in order
            to have a working and complete implementation of the c2w
            protocol.
        """
        #: The serverProxy, which the protocol must use
        #: to interact with the server (to access the movie list and to 
        #: access and modify the user list).

        self.serverProxy = serverProxy
        self.lossPr = lossPr
        self.List_User = []
        # Initialisation de l'event Id
        self.Last_event_Id = -1
        
        # Liste des films
        self.MovieList = self.serverProxy.getMovieList()
        self.Nbr_Movie=0
        
        # Liste des identifiants des movies rooms
        self.listeIdRoom=[]
        
        # Initialisation des buffers qu'on va utiliser pour le Response Event
        self.buf_switch = bytearray(0)
        self.buf_new_msg = bytearray(0)
        self.buf_logout = bytearray(0)
        self.buf_new_user = bytearray(0)
        
        # Liste des timers
        self.timer=[]
        # Dernier paquet reçu
        self.datagram=bytearray(0)
        # Derniière réponse envoyée
        self.response= bytearray(0)
        # L'adresse et le port du dernier utilisateur qui envoyé un paquet
        self.host_port=(0,0)

        self.bool= False


    def startProtocol(self):
        """
        DO NOT MODIFY THE FIRST TWO LINES OF THIS METHOD!!

        If in doubt, do not add anything to this method.  Just ignore it.
        It is used to randomly drop outgoing packets if the -l
        command line option is used.
        """
        self.transport = LossyTransport(self.transport, self.lossPr)
        DatagramProtocol.transport = self.transport

    # Méthode qui incrémente l'event Id
    def increment_Event_Id(self) :
        if (self.Last_event_Id > 65536) :
            self.Last_event_Id = 0
        else :
            self.Last_event_Id += 1

    # Méthode à exécuter si on ne reçoit pas de ping après 60s

    def verifyResponse(self, parameter):

        user_id_list=[]
        for i in self.serverProxy.getUserList():
            user_id_list.append(i.userId)
        if parameter in user_id_list:
            increment_Event_Id(self)
            # Formation du paquet à envoyer dans le response event (evenement: suppression d'un utilisateur)
            
            # Determination de l'identifiant du room dans laquelle l'utilisateur se trouve
            Room_Name = self.serverProxy.getUserById(parameter).userChatRoom
            if Room_Name == ROOM_IDS.MAIN_ROOM:
                RoomId = 0
            else:
                RoomId = self.serverProxy.getMovieByTitle(Room_Name).movieId
            # Last_Event_Id
            a=(self.Last_event_Id & int('111111111111111100000000',2)) >> 8
            b=(self.Last_event_Id) & 255

            # Message_data
            buf = struct.pack('!HBBBB',a,b,0x4,RoomId,parameter)
            # Supression de l'utilisateur'
            self.serverProxy.removeUser(self.serverProxy.getUserById(parameter).userName)
            self.buf_logout += buf  # Formation petit à petit du buf à envoyer dans le response event pour l'event logout

    def datagramReceived(self, datagram, host_port):
        """
        :param string datagram: the payload of the UDP packet.
        :param host_port: a touple containing the source IP address and port.
        
        Twisted calls this method when the server has received a UDP
        packet.  You cannot change the signature of this method.
        """
        
        
        # Récupération de l'entete
        (Message_Type,Seq_Number,User_ID,Message_Length)=struct.unpack('!BHBH',datagram[:6]) 

        # Si on reçoit le meme paquet une deuxième fois
        if self.datagram == datagram : 
            if host_port == self.host_port :
                self.transport.write(self.response, host_port)

        else:
            self.datagram=datagram
            self.host_port= host_port
        
    #----------------------------- RESPONSE-LOGIN -----------------------------------------------

            if Message_Type == 0x00:

                # Recupération du data
                (UL,Username)=struct.unpack('!B'+str(Message_Length-1)+'s',datagram[6:])

                # Récupération de la liste des utilisateurs
                self.List_User=self.serverProxy.getUserList()

                # Détermination du status_Code

                i = 0
                for n in self.List_User:
                    if n.userName == Username.decode('utf-8') : # Si le nom d'utilisateur existe déjà dans la liste
                        i = 1
                        User_Id = 0
                if i == 1:
                    Status_Code = 4 # USERNAME-NOT_AVIALABLE
                else:
                    Status_Code = 0 # SUCCESS
                    self.List_User.append(Username)
                    
                    # Ajout de l'utilisateur à la liste et génération de User_ID
                    User_Id = self.serverProxy.addUser(Username.decode('utf-8'),ROOM_IDS.MAIN_ROOM,userAddress = host_port[0])

                    # Incrémentation de l'event Id
                    increment_Event_Id(self)
                    a=(self.Last_event_Id & int('111111111111111100000000',2)) >> 8
                    b=(self.Last_event_Id) & 255
                    # Message_data
                    buf = struct.pack('!HBBBBB'+str(UL)+'s',a,b,0x2,0x0,User_Id,UL,Username)
                    self.buf_new_user += buf  # Formation petit a petit du buf a envoyer dans le response event pour l'event new user

                if User_Id > 255 :
                    Status_Code = 2 # TOO_MANY_USERS

                # Construction et envoi de la réponse
                a=(self.Last_event_Id & int('111111111111111100000000',2)) >> 8
                b=(self.Last_event_Id) & 255             
                Response_Login=struct.pack('!BHBHBBHB',0x01,Seq_Number,0,5,Status_Code,User_Id,a,b)
                self.transport.write(Response_Login, host_port)
                self.response= Response_Login
                # Lancement du Timer
                self.timer.append(reactor.callLater(60, self.verifyResponse, User_Id))

    #----------------------------- RESPONSE-ROOMS -----------------------------------------------
            
            if Message_Type == 0x08:

                # Récupération du data
                (First_Room_Id,Nbr_Rooms)=struct.unpack('!BB',datagram[6:])
                NbrMovie = 0
                # Calcul du Message Length
                Msg_Length = 0
                for i in self.MovieList:
                    if (i.movieId >= First_Room_Id) and (i.movieId <= First_Room_Id + Nbr_Rooms):
                        Msg_Length += len(i.movieTitle) + 9
                        NbrMovie += 1

                # Formation de l'entete
                UserList = self.serverProxy.getUserList()
                buf = bytearray(0)
                buf += struct.pack('!BHBHB',9,Seq_Number,0,Msg_Length+1,NbrMovie)

                # Formation du message
                self.MovieList = self.serverProxy.getMovieList()

                for i in self.MovieList:
                    # Parcours de la liste des videos disponibles
                    if (i.movieId >= First_Room_Id) and (i.movieId <= First_Room_Id + Nbr_Rooms):
                        (addr_IP, Movie_Port)= self.serverProxy.getMovieAddrPort(i.movieTitle)
                        Video_Name = i.movieTitle
                        Nbr = 0
                        for j in UserList:
                            if Video_Name == j.userChatRoom:
                                Nbr += 1
                        ip=addr_IP.split('.')
                        RNL = len(i.movieTitle)
                        # Construction de la réponse
                        buf += struct.pack('!B4B',i.movieId,int(ip[0]),int(ip[1]),int(ip[2]),int(ip[3]))
                        buf += struct.pack('!HB'+str(RNL)+'sB',Movie_Port,RNL,(i.movieTitle).encode('utf-8'),Nbr)
                self.transport.write(buf, host_port)
                self.response = buf

            
    #----------------------------- RESPONSE_USERS -----------------------------------------------

            if Message_Type == 0x0A:
                
                # Récupération du data
                (First_User_Id,Nbr_Users,Room_Id)=struct.unpack('!BBB',datagram[6:])
                
                # Récupération de la liste des utilisateurs
                UserList = self.serverProxy.getUserList()
                LenUserList = len(self.serverProxy.getUserList())
                
                self.Nbr_Movie = len(self.MovieList)
                n=0

                # Si l'utilisateur demande la liste d'une room précise
                if Room_Id != 0x00:
                    # calcul de la longueur du message
                    Msg_Length = 0
                    Nbr = 0 # Nombre d'utlisateurs dans le movie room
                    e=0
                    Video_Name = self.serverProxy.getMovieById(Room_Id).movieTitle
                    for i in UserList:
                            if Video_Name == i.userChatRoom:
                                Msg_Length += len(i.userName) + 3
                                Nbr += 1

                    # construction de l'entete
                    buf = bytearray(0)
                    buf = struct.pack('!BHBHB',11,Seq_Number,0,Msg_Length+1,Nbr)

                    for i in UserList:
                            if Video_Name == i.userChatRoom:
                                if (i.userId>= First_User_Id) and (i.userId < First_User_Id + Nbr_Users):
                                    UL = len(i.userName)
                                    buf+= struct.pack('!BB'+str(UL)+'sB',i.userId,UL,(i.userName).encode('utf-8'),Room_Id)
 

                # si l'utilisateur demande le liste des utilisateurs dans toutes les rooms
                if Room_Id == 0x00:
                    # calcul de la longueur du message
                    Msg_Length = 0
                    buf=bytearray(0)
                    for i in UserList:
                        Msg_Length += len(i.userName) + 3

                    # Entete
                    buf=struct.pack('!BHBHB',11,Seq_Number,0,Msg_Length+1,len(UserList))
                    
                    e=0
                    # Récupération des listes des clients pour chaque movie room
                    for i in self.MovieList:
                        if i.movieId not in self.listeIdRoom:
                            self.listeIdRoom.append(i.movieId)
                    listeIdRoom=self.listeIdRoom
                    listeIdRoom.append(0)
                    for RoomId in listeIdRoom:
                        if RoomId!=0 :
                            Video_Name = self.serverProxy.getMovieById(RoomId).movieTitle
                            for i in UserList:
                                if (Video_Name == i.userChatRoom):
                                    if (i.userId >= First_User_Id) and (i.userId < First_User_Id + Nbr_Users):
                                            UL = len(i.userName)    
                                            buf+=struct.pack('!BB'+str(UL)+'sB',i.userId,UL,(i.userName).encode('utf-8'),RoomId)
                        elif e==0:
                                e+=1
                                for i in UserList:
                                    if (i.userChatRoom == ROOM_IDS.MAIN_ROOM):
                                        if (i.userId >= First_User_Id) and (i.userId < First_User_Id + Nbr_Users):
                                            UL = len(i.userName)
    #                                       struct.pack_into('!BB'+str(UL)+'sB',buf,7+n,i.userId,UL,(i.userName).encode('utf-8'),0)
    #                                       n += 3 + UL
                                            buf+=struct.pack('!BB'+str(UL)+'sB',i.userId,UL,(i.userName).encode('utf-8'),RoomId)
                            
                self.transport.write(buf, host_port)
                self.response = buf

    #----------------------------- RESPONSE_MESSAGE -----------------------------------------------
            
            if Message_Type == 0x0E:

                # Récupération du data
                (Room_Id,Msg_Length,Message_Content)=struct.unpack('!BH'+str(Message_Length-3)+'s',datagram[6:])

                # Détermination de roomID du client
                Room_Name = (self.serverProxy.getUserById(User_ID)).userChatRoom
                if Room_Name == ROOM_IDS.MAIN_ROOM:
                    RoomId = 0
                else:
                    RoomId = self.serverProxy.getMovieByTitle(Room_Name).movieId
                # Détermination du Status_Code
                if int(Room_Id) == RoomId:
                    Status_Code = 0
                    increment_Event_Id(self)
                    a=(self.Last_event_Id & int('111111111111111100000000',2)) >> 8
                    b=(self.Last_event_Id) & 255
                    # Construction de la réponse
                    buf=bytearray(0)
                    buf = struct.pack('!HBBBBH'+str(Msg_Length)+'s',a,b,0x1,Room_Id,User_ID,Msg_Length,Message_Content)

                    self.buf_new_msg += buf    # Formation petit a petit du buf a envoyer dabs le response event pour l'event new message
                elif int(Room_Id) != RoomId:
                    if RoomId in self.listeIdRoom:
                        Status_Code = 3
                    else:
                        Status_Code = 2
                else:
                    Status_Code = 1
                Response_Message=struct.pack('!BHBHB',0x0F,Seq_Number,0,1,Status_Code)
                
                self.transport.write(Response_Message, host_port)
                self.response = Response_Message
                
            
    #----------------------------- RESPONSE_PING -----------------------------------------------

            if Message_Type == 0x04:

                self.timer[User_ID-1].reset(60)

                # Récupération du data
                (LastEventId_a,LastEventId_b,Room_Id)=struct.unpack('!HBB',datagram[6:])
                a=(self.Last_event_Id & int('111111111111111100000000',2)) >> 8
                b=(self.Last_event_Id) & 255             
                # Construction et envoi de la réponse
                Response_Ping=struct.pack('!BHBHHB',0x05,Seq_Number,0,3,a,b)

                self.transport.write(Response_Ping, host_port)
                self.response = Response_Ping
                
    #----------------------------- RESPONSE_SWITCH_ROOM -----------------------------------------

            if Message_Type == 0x0C:
                # Récupération du data
                (Room_Id)=struct.unpack('!B',datagram[6:])
                userlist = self.serverProxy.getUserList()

                # Détermination du room ID du client =RoomId
                Room_Name = self.serverProxy.getUserById(User_ID).userChatRoom
                if Room_Name == ROOM_IDS.MAIN_ROOM:
                    RoomId = 0
                else:
                    RoomId = self.serverProxy.getMovieByTitle(Room_Name).movieId
                # Détermination du Status_Code
                if Room_Id[0] == RoomId:
                    Status_Code = 1
                elif (RoomId != 0) and (Room_Id[0] != 0):
                    Status_Code = 1
                elif (Room_Id[0] not in self.listeIdRoom):
                    Status_Code = 1

                else:
                	
                    Status_Code = 0
                    if (Room_Id[0] != 0):
                    	for i in userlist: #on verifie si il y a encore des clients dans la room
                    		if self.serverProxy.getMovieById(Room_Id[0]).movieTitle == i.userChatRoom:
                    			p=1
                    		else:
                    			p=0
                    	if p==0:
                    		#si il n' y a plus personne dans la room:  Start streaming lorsque le client quitte le main room vers un movie room
                    		self.serverProxy.startStreamingMovie(self.serverProxy.getMovieById(int(Room_Id[0])).movieTitle)
                    else:
                    	for i in userlist: #on verifie si il y a encore des clients dans la room
                    		if self.serverProxy.getMovieById(RoomId).movieTitle == i.userChatRoom:
                    			p=1
                    		else:
                    			p=0
                    	if p==0:
                    		# si il n' y a plus personne dans la room: Stop streaming lorsque le client quitte un movie room
                    		self.serverProxy.stopStreamingMovie(self.serverProxy.getMovieById(int(RoomId)).movieTitle)
                    if Room_Id[0] == 0 :
                        self.serverProxy.updateUserChatroom(self.serverProxy.getUserById(User_ID).userName, ROOM_IDS.MAIN_ROOM)
                    else :
                        self.serverProxy.updateUserChatroom(self.serverProxy.getUserById(User_ID).userName, self.serverProxy.getMovieById(int(Room_Id[0])).movieTitle)
                    increment_Event_Id(self)
                    a=(self.Last_event_Id & int('111111111111111100000000',2)) >> 8
                    b=(self.Last_event_Id) & 255             
                    #buf = struct.pack('!HBBBBB',a,b,0x3,Room_Id[0],User_ID,int(Room_Id[0]))
                    buf = struct.pack('!HBBBBB',a,b,0x3,RoomId,User_ID,Room_Id[0])
                    self.buf_switch += buf          #formation petit a petit du buf a envoyer dabs le response event pour l'event switch room
                Response_Switch_Room=struct.pack('!BHBHB',0x0D,Seq_Number,0,1,Status_Code)

                self.transport.write(Response_Switch_Room, host_port)
                self.response = Response_Switch_Room
            
    #----------------------------- RESPONSE_LOGOUT -----------------------------------------------

            if Message_Type == 0x02:
                # Détermination du room Id du client
                Room_Name = self.serverProxy.getUserById(User_ID).userChatRoom
                if Room_Name == ROOM_IDS.MAIN_ROOM:
                    RoomId = 0
                else:
                    RoomId = self.serverProxy.getMovieByTitle(Room_Name).movieId
                if RoomId == 0:
                    Status_Code = 0
                    # Supression du client de la liste
                    self.serverProxy.removeUser(self.serverProxy.getUserById(User_ID).userName)
                    increment_Event_Id(self)
                    a=(self.Last_event_Id & int('111111111111111100000000',2)) >> 8
                    b=(self.Last_event_Id) & 255             
                    buf = struct.pack('!HBBBB',a,b,0x4,RoomId,User_ID)
                    self.buf_logout += buf  #formation petit a petit du buf a envoyer dans le response event pour l'event logout
 
                    self.timer[User_ID-1].cancel()
                    userList=self.serverProxy.getUserList()

                else:
                    Status_Code = 1
                Response_Logout=struct.pack('!BHBHB',0x03,Seq_Number,0,1,Status_Code)
                self.transport.write(Response_Logout, host_port)
                self.response = Response_Logout
                

    #----------------------------- RESPONSE_EVENTS -----------------------------------------------

            if Message_Type == 0x06:
                # Récupération du data
                (LastEventId_a,LastEventId_b,Nbr_Events,Room_Id)=struct.unpack('!HBBB',datagram[6:])
                LastEventId = (LastEventId_a<<8)|LastEventId_b
                buf = bytearray(0)
                event_nbr=0
                v=0
                i=0
                p=0
                

                
                # Si l'utilisateur demande les événements d'un room précis
                if Room_Id != 0: 
                 # Event : new message
                    while(i <= len(self.buf_new_msg)-1):
                        taille_msg = struct.unpack('!H',self.buf_new_msg[i+6:i+8])
                        p = int(taille_msg[0]) + 8
                        v += p
                        if (self.buf_new_msg[i+4] == Room_Id) and ( ( (self.buf_new_msg[i]<<16) | (self.buf_new_msg[i+1]<<8) | self.buf_new_msg[i+2]) > LastEventId):
                            buf += self.buf_new_msg[i:v]
                            event_nbr+=1
                        i+=p
                # Event : new user
                    v=0
                    i=0
                    p=0

                    while(i <= len(self.buf_new_user)-1):
                        ul = self.buf_new_user[i+6]
                        p = int(ul) + 7
                        v+=p
                        if (( (self.buf_new_user[i]<<16) | (self.buf_new_user[i+1]<<8) | self.buf_new_user[i+2]) >LastEventId):
                            buf += self.buf_new_user[i:v]
                            event_nbr+=1
                        i+=p
                # Event : logout
                    p = 0
                    i = 0
                    v = 0

                    while(i <= len(self.buf_logout)-1):
                        p = 6
                        v+=p
                        if (((self.buf_logout[i]<<16) | (self.buf_logout[i+1]<<8) | self.buf_logout[i+2]) > LastEventId ):
                        #if (self.buf_logout[i+4] == Room_Id) and (((self.buf_logout[i]<<16) | (self.buf_logout[i+1]<<8) | self.buf_logout[i+2]) > LastEventId ):
                            buf += self.buf_logout[i:v]
                            event_nbr+=1
                        i+=p
                # Event : switch room
                    i=0
                    v=0
                    p=0
                    
                    while(i <= len(self.buf_switch)-1):
                        p = 7
                        v+=p
                        if (self.buf_switch[i+6] == Room_Id ) and (( (self.buf_switch[i]<<16) | (self.buf_switch[i+1]<<8) | self.buf_switch[i+2]) > LastEventId):
                            buf += self.buf_switch[i:v]

                            event_nbr+=1
                        if (self.buf_switch[i+6] == 0 ) and (( (self.buf_switch[i]<<16) | (self.buf_switch[i+1]<<8) | self.buf_switch[i+2]) > LastEventId):
                            buf += self.buf_switch[i:v]

                            event_nbr+=1
                        i+=p
                    buf1 =struct.pack('!BHBHB',0x07,Seq_Number,0,len(buf)+1,event_nbr)
                    buf1 += buf
                    
                # Si l'utilisateur demande tous les événements 
                else:
                 # Event : new message
                    p = 0
                    i = 0

                    while(i <= len(self.buf_new_msg)-1):
                        taille_msg = struct.unpack('!H',self.buf_new_msg[i+6:i+8])
                        p = int(taille_msg[0]) + 8
                        v += p
                        if ( ( (self.buf_new_msg[i]<<16) | (self.buf_new_msg[i+1]<<8) | self.buf_new_msg[i+2]) > LastEventId):
                            buf += self.buf_new_msg[i:v]

                        i += p
                 # Event : new user
                    p = 0
                    i = 0
                    v=0
                    while(i <= len(self.buf_new_user)-1):
                        ul = self.buf_new_user[i+6]
                        p = int(ul) + 7
                        v+=p
                        if (( (self.buf_new_user[i]<<16) | (self.buf_new_user[i+1]<<8) | self.buf_new_user[i+2]) > LastEventId):
                            
                            buf += self.buf_new_user[i:v]
                        i += p
                 # Event : logout
                    p = 0
                    i = 0
                    v=0

                    while(i <= len(self.buf_logout)-1):
                        p = 6
                        v+=p
                        if (((self.buf_logout[i]<<16) | (self.buf_logout[i+1]<<8) | self.buf_logout[i+2]) > LastEventId ):
                            buf += self.buf_logout[i:v]
                        i += p
                 # Event : switch room
                    p = 0
                    i = 0
                    v=0


                    while(i <= len(self.buf_switch)-1):
                        p = 7
                        v+=p

                        if (( (self.buf_switch[i]<<16) | (self.buf_switch[i+1]<<8) | self.buf_switch[i+2] ) > LastEventId):
                            buf += self.buf_switch[i:v]
                        i += p

                    p = 0
                    i = 0


                    buf1 = struct.pack('!BHBHB',0x07,Seq_Number,0,len(buf)+1,Nbr_Events)
                    buf1 += buf
                self.transport.write(buf1, host_port)
                self.response = buf1
        pass
