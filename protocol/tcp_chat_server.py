# -*- coding: utf-8 -*-
from twisted.internet.protocol import Protocol
import logging
import struct
import sys
import c2w
from twisted.internet import reactor
from c2w.main.constants import ROOM_IDS

logging.basicConfig()
moduleLogger = logging.getLogger('c2w.protocol.tcp_chat_server_protocol')


class c2wTcpChatServerProtocol(Protocol):


    # Initialisation de l'event Id
    Last_event_Id = -1
    # Liste des films
    Nbr_Movie=0
    MovieList = []
    List_User = []
    # Liste des identifiants des movies rooms
    listeIdRoom=[]
    # Initialisation des buffers qu'on va utiliser pour le Response Event
    buf_switch = bytearray(0)
    buf_new_msg = bytearray(0)
    buf_logout = bytearray(0)
    buf_new_user = bytearray(0)
    def __init__(self, serverProxy, clientAddress, clientPort):
        """
        :param serverProxy: The serverProxy, which the protocol must use
            to interact with the user and movie store (i.e., the list of users
            and movies) in the server.
        :param clientAddress: The IP address (or the name) of the c2w server,
            given by the user.
        :param clientPort: The port number used by the c2w server,
            given by the user.

        Class implementing the TCP version of the client protocol.

        .. note::
            You must write the implementation of this class.

        Each instance must have at least the following attribute:

        .. attribute:: serverProxy

            The serverProxy, which the protocol must use
            to interact with the user and movie store in the server.

        .. attribute:: clientAddress

            The IP address of the client corresponding to this 
            protocol instance.

        .. attribute:: clientPort

            The port number used by the client corresponding to this 
            protocol instance.

        .. note::
            You must add attributes and methods to this class in order
            to have a working and complete implementation of the c2w
            protocol.

        .. note::
            The IP address and port number of the client are provided
            only for the sake of completeness, you do not need to use
            them, as a TCP connection is already associated with only
            one client.
        """
        #: The IP address of the client corresponding to this 
        #: protocol instance.
        self.clientAddress = clientAddress
        #: The port number used by the client corresponding to this 
        #: protocol instance.
        self.clientPort = clientPort
        #: The serverProxy, which the protocol must use
        #: to interact with the user and movie store in the server.
        self.serverProxy = serverProxy
        # Dernier paquet reçu
        self.datagram=bytearray(0)
        # Dernière réponse envoyée
        self.response=bytearray(0)
        self.data=bytearray(0)



    # Méthode qui incrémente l'event Id 
    def increment_Event_Id(self) :
        if (c2wTcpChatServerProtocol.Last_event_Id > 2^8-1) :
            c2wTcpChatServerProtocol.Last_event_Id = 0
        else :
            c2wTcpChatServerProtocol.Last_event_Id += 1
            
    # Méthode à exécuter si on ne reçoit pas de ping après 60s
    def verifyResponse(self, parameter):
    
        self.increment_Event_Id()
   # Formation du datagramme à envoyer dans le response event (evenement: suppression d'un utilisateur)
        # Determination de l'identifiant du room dans laquelle l'utilisateur se trouve
        Room_Name = self.serverProxy.getUserById(parameter).userChatRoom
        if Room_Name == ROOM_IDS.MAIN_ROOM:
            RoomId = 0
        else:
            RoomId = self.serverProxy.getMovieByTitle(Room_Name).movieId
        # Last_Event_Id
        a=(c2wTcpChatServerProtocol.Last_event_Id & int('111111111111111100000000',2)) >> 8
        b=(c2wTcpChatServerProtocol.Last_event_Id) & 255

        # Message_data
        buf = struct.pack('!HBBBB',a,b,0x4,RoomId,parameter)
        # Supression de l'utilisateur
        self.serverProxy.removeUser(self.serverProxy.getUserById(parameter).userName)
        c2wTcpChatServerProtocol.buf_logout += buf  # Formation petit à petit du buf à envoyer dans le response event pour l'event logout


    def dataReceived(self, data):
        """
        :param data: The data received from the client (not necessarily
                     an entire message!)

        Twisted calls this method whenever new data is received on this
        connection.
        """

        c2wTcpChatServerProtocol.MovieList = self.serverProxy.getMovieList()
        self.datagram += data
        # Taille du paquet reçu
        n = len(self.datagram)
        print(data)
        # Si la taille est supérieure à 6, donc on a reçu l'entete
        if n>6:

            #Récupération de l'entete
            (Message_Type,Seq_Number,User_ID,Message_Length)=struct.unpack('!BHBH',self.datagram[:6])
            # Si la taille est supérieure à Message_Length+6, on a reçu tout le paquet
            if n >= Message_Length+6:
            # Si on reçoit le meme datagramme une deuxième fois
                if self.data == self.datagram : 
                    self.transport.write(self.response)

                else:
                    self.data=self.datagram[:6+Message_Length]
                    
#----------------------------- RESPONSE-LOGIN -----------------------------------------------
                    if Message_Type == 0x00:

                        # Recupération du data
                        (UL,Username)=struct.unpack('!B'+str(Message_Length-1)+'s',self.datagram[6:6+Message_Length])

                        # Récupération de la liste des utilisateurs
                        c2wTcpChatServerProtocol.List_User=self.serverProxy.getUserList()

                        # Détermination du status_Code
                        i=0
                        for n in c2wTcpChatServerProtocol.List_User:
                            if n.userName == Username.decode('utf-8') : # Si le nom d'utilisateur existe déjà dans la liste
                                i = 1
                                User_Id = 0
                        if i == 1:
                            Status_Code = 4 # USERNAME-NOT_AVIALABLE
                        else:
                            Status_Code = 0 # SUCCESS
                    # Ajout de l'utilisateur à la liste et génération de User_ID
                            c2wTcpChatServerProtocol.List_User.append(Username)
                            User_Id = self.serverProxy.addUser(Username.decode('utf-8'),ROOM_IDS.MAIN_ROOM)
                    # Incrémentation de l'event Id
                            self.increment_Event_Id()
                            a=(c2wTcpChatServerProtocol.Last_event_Id & int('111111111111111100000000',2)) >> 8
                            b=(c2wTcpChatServerProtocol.Last_event_Id) & 255             
                    # Message_data 
                            buf = struct.pack('!HBBBBB'+str(UL)+'s',a,b,0x2,0x0,User_Id,UL,Username)
                            c2wTcpChatServerProtocol.buf_new_user += buf  #formation petit a petit du buf a envoyer dans le response event pour l'event new user
                        if User_Id > 255 :
                            Status_Code = 2
                        # Construction et envoi de la réponse
                        a=(c2wTcpChatServerProtocol.Last_event_Id & int('111111111111111100000000',2)) >> 8
                        b=(c2wTcpChatServerProtocol.Last_event_Id) & 255             
                        Response_Login=struct.pack('!BHBHBBHB',0x01,Seq_Number,0,5,Status_Code,User_Id,a,b)
                        self.transport.write(Response_Login)
                        self.response= Response_Login
                        self.datagram=bytearray(0)
                        # Lancement du timer
                        self.callID = reactor.callLater(60, self.verifyResponse, User_Id)
                
                    
#----------------------------- RESPONSE-ROOMS -----------------------------------------------
                    
                    if Message_Type == 0x08:

                        # Récupération du data
                        (First_Room_Id,Nbr_Rooms)=struct.unpack('!BB',self.datagram[6:6+Message_Length])
                        NbrMovie = 0
                        # Calcul du Message Length
                        for i in c2wTcpChatServerProtocol.MovieList:
                            Msg_Length = 0
                            if (i.movieId >= First_Room_Id) and (i.movieId <= First_Room_Id + Nbr_Rooms):
                                Msg_Length += len(i.movieTitle) + 9
                                NbrMovie += 1

                        # Formation de l'entete
                        buf = bytearray(0)
                        UserList = self.serverProxy.getUserList()
                        buf += struct.pack('!BHBHB',9,Seq_Number,0,Msg_Length+1,NbrMovie)

                        # Message_data
                        c2wTcpChatServerProtocol.MovieList = self.serverProxy.getMovieList()

                        for i in c2wTcpChatServerProtocol.MovieList:
                            # Parcours de la liste des videos disponibles
                            if (i.movieId >= First_Room_Id) and (i.movieId <= First_Room_Id + Nbr_Rooms):
                                (addr_IP, Movie_Port)= self.serverProxy.getMovieAddrPort(i.movieTitle)
                                Video_Name = i.movieTitle
                                Nbr = 0 # Nombre d'utilisateurs dans chaque room
                                # Détermination du nombre d'utilisateurs dans chaque room
                                for j in UserList:
                                    if Video_Name == j.userChatRoom:
                                        Nbr += 1 
                                # adresse IP du video
                                ip=addr_IP.split('.')
                                # Taille du nom de video
                                RNL = len(i.movieTitle)
                                # Construction de la réponse
                                buf += struct.pack('!B4B',i.movieId,int(ip[0]),int(ip[1]),int(ip[2]),int(ip[3]))
                                buf += struct.pack('!HB'+str(RNL)+'sB',Movie_Port,RNL,(i.movieTitle).encode('utf-8'),Nbr)
                        # Envoi de la réponse
                        self.transport.write(buf) 
                        self.response=buf
                        self.datagram=bytearray(0)
                        print(buf)

                    
#----------------------------- RESPONSE_USERS -----------------------------------------------

                    if Message_Type == 0x0A:
                        
                        # Récupération du data
                        (First_User_Id,Nbr_Users,Room_Id)=struct.unpack('!BBB',self.datagram[6:6+Message_Length])
                        
                        # Récupération de la liste des utilisateurs
                        UserList = self.serverProxy.getUserList()
                        LenUserList = len(self.serverProxy.getUserList())
                        # Nombre de videos
                        c2wTcpChatServerProtocol.Nbr_Movie = len(c2wTcpChatServerProtocol.MovieList)
                        object_user= self.serverProxy.getUserById(User_ID)
                        n=0

                        #si l'utilisateur demande la liste d'une room précise
                        if Room_Id != 0x00:
                            # calcul de la longueur du message
                            Msg_Length = 0
                            Nbr = 0 # Nombre d'utlisateurs dans le movie room
                            
                            # Détermination du nombre d'utilisateurs dans chaque movie room
                            Video_Name = self.serverProxy.getMovieById(Room_Id).movieTitle
                            for i in UserList:
                                    if Video_Name == i.userChatRoom:
                                        Msg_Length += len(i.userName) + 3
                                        Nbr += 1

                            # construction de l'entete
                            buf = bytearray(0)
                            buf = struct.pack('!BHBHB',11,Seq_Number,0,Msg_Length+1,Nbr)
                            # Message_data
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
                            for i in c2wTcpChatServerProtocol.MovieList:
                                if i.movieId not in self.listeIdRoom: # Liste des room Id
                                    self.listeIdRoom.append(i.movieId)
                            listeIdRoom=self.listeIdRoom
                            listeIdRoom.append(0)

                            # Récupération des listes des clients pour chaque movie room
                            for RoomId in listeIdRoom:
                                if RoomId!=0 :
                                    Video_Name = self.serverProxy.getMovieById(RoomId).movieTitle
                                    for i in UserList:
                                        if (Video_Name == i.userChatRoom):
                                            if (i.userId >= First_User_Id) and (i.userId < First_User_Id + Nbr_Users):
                                                    UL = len(i.userName)   
                                                    # Ajout de l'utilisateur au buffer
                                                    buf+=struct.pack('!BB'+str(UL)+'sB',i.userId,UL,(i.userName).encode('utf-8'),RoomId)
                                # Nombre d'utilisateurs dans le main room
                                elif e==0:
                                        e+=1
                                        for i in UserList:
                                            if (i.userChatRoom == ROOM_IDS.MAIN_ROOM):
                                                if (i.userId >= First_User_Id) and (i.userId < First_User_Id + Nbr_Users):
                                                    UL = len(i.userName)
                                                    buf+=struct.pack('!BB'+str(UL)+'sB',i.userId,UL,(i.userName).encode('utf-8'),RoomId)
                                    
                        self.transport.write(buf)
                        self.response=buf
                        self.datagram=bytearray(0)

#----------------------------- RESPONSE_MESSAGE -----------------------------------------------
                    
                    if Message_Type == 0x0E:

                        # Récupération du data
                        (Room_Id,Msg_Length,Message_Content)=struct.unpack('!BH'+str(Message_Length-3)+'s',self.datagram[6:6+Message_Length])

                        # Détermination de roomID du client
                        Room_Name = (self.serverProxy.getUserById(User_ID)).userChatRoom
                        if Room_Name == ROOM_IDS.MAIN_ROOM:
                            RoomId = 0
                        else:
                            RoomId = self.serverProxy.getMovieByTitle(Room_Name).movieId
                        # Détermination du Status_Code
                        if int(Room_Id) == RoomId:
                            Status_Code = 0 # SUCCESS
                            # incrémentation de l'event id
                            self.increment_Event_Id()
                            a=(c2wTcpChatServerProtocol.Last_event_Id & int('111111111111111100000000',2)) >> 8
                            b=(c2wTcpChatServerProtocol.Last_event_Id) & 255
                            # Construction de la réponse
                            buf=bytearray(0)
                            buf = struct.pack('!HBBBBH'+str(Msg_Length)+'s',a,b,0x1,Room_Id,User_ID,Msg_Length,Message_Content)

                            c2wTcpChatServerProtocol.buf_new_msg += buf    # Formation petit a petit du buf a envoyer dabs le response event pour l'event new message
                        elif int(Room_Id) != RoomId:
                            if RoomId in self.listeIdRoom: # Si l'utilisateur envoie un roomID different de celui du room dans laquelle il se trouve
                                Status_Code = 3 # INCORRECT_ROOM
                            else:
                                Status_Code = 2 # INVALID_ROOM
                        else:
                            Status_Code = 1 # UNKNOWN ERROR
                        # Envoi de la réponse
                        Response_Message=struct.pack('!BHBHB',0x0F,Seq_Number,0,1,Status_Code)

                        self.transport.write(Response_Message)
                        self.response=Response_Message
                        self.datagram=bytearray(0)
                    
#----------------------------- RESPONSE_PING -----------------------------------------------

                    if Message_Type == 0x04:

                        (self.callID).reset(60)
                        # Récupération du data
                        (LastEventId_a,LastEventId_b,Room_Id)=struct.unpack('!HBB',self.datagram[6:6+Message_Length])
                        # Last_Event_Id
                        a=(c2wTcpChatServerProtocol.Last_event_Id & int('111111111111111100000000',2)) >> 8
                        b=(c2wTcpChatServerProtocol.Last_event_Id) & 255             
                        # Construction et envoi de la réponse
                        Response_Ping=struct.pack('!BHBHHB',0x05,Seq_Number,0,3,a,b)

                        self.transport.write(Response_Ping)
                        self.response=Response_Ping
                        self.datagram=bytearray(0)
                        
#----------------------------- RESPONSE_SWITCH_ROOM -----------------------------------------

                    if Message_Type == 0x0C:
                        # Récupération du data
                        (Room_Id)=struct.unpack('!B',self.datagram[6:6+Message_Length])
                        userlist= self.serverProxy.getUserList()

                        # Détermination du room ID
                        Room_Name = self.serverProxy.getUserById(User_ID).userChatRoom
                        if Room_Name == ROOM_IDS.MAIN_ROOM:
                            RoomId = 0
                        else:
                            RoomId = self.serverProxy.getMovieByTitle(Room_Name).movieId
                        # Détermination du Status_Code
                        if Room_Id[0] == RoomId:
                            Status_Code = 1 # ERROR : L'utilisateur doit envoyer un room id different de son room id pour faire un switch
                        elif (RoomId != 0) and (Room_Id[0] != 0):
                            Status_Code = 1 # ERROR : Si l'utilisateur est dans un movie room, il ne peut faire un switch que vers le main room
                        elif (Room_Id[0] not in self.listeIdRoom):
                            Status_Code = 1 # ERROR: si l'utilisateur envoie un room id qui n'existe pas 
                        else:

                            Status_Code = 0 # SUCCESS
                            # Si l'utilisateur veut faire un switch vers un movie room
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
                            # Modification du statut de l'utilisateur
                            if Room_Id[0] == 0 :
                                self.serverProxy.updateUserChatroom(self.serverProxy.getUserById(User_ID).userName, ROOM_IDS.MAIN_ROOM)
                            else :
                                self.serverProxy.updateUserChatroom(self.serverProxy.getUserById(User_ID).userName, self.serverProxy.getMovieById(int(Room_Id[0])).movieTitle)
                            # Last_Event_Id
                            self.increment_Event_Id()
                            a=(c2wTcpChatServerProtocol.Last_event_Id & int('111111111111111100000000',2)) >> 8
                            b=(c2wTcpChatServerProtocol.Last_event_Id) & 255             
                            # Message_data
                            buf = struct.pack('!HBBBBB',a,b,0x3,RoomId,User_ID,Room_Id[0])
                            c2wTcpChatServerProtocol.buf_switch += buf          #formation petit a petit du buf a envoyer dabs le response event pour l'event switch room
                        Response_Switch_Room=struct.pack('!BHBHB',0x0D,Seq_Number,0,1,Status_Code)

                        self.transport.write(Response_Switch_Room)
                        self.response=Response_Switch_Room
                        self.datagram=bytearray(0)
                    
#----------------------------- RESPONSE_LOGOUT -----------------------------------------------

                    if Message_Type == 0x02:
                        # Détermination du room Id du client
                        Room_Name = self.serverProxy.getUserById(User_ID).userChatRoom
                        if Room_Name == ROOM_IDS.MAIN_ROOM:
                            RoomId = 0
                        else:
                            RoomId = self.serverProxy.getMovieByTitle(Room_Name).movieId
                        # Si l'utilisateur est dans le main room
                        if RoomId == 0:
                            Status_Code = 0 # SUCCESS
                            # Supression du client de la liste
                            self.serverProxy.removeUser(self.serverProxy.getUserById(User_ID).userName)
                            # Last_Event_Id
                            self.increment_Event_Id()
                            a=(c2wTcpChatServerProtocol.Last_event_Id & int('111111111111111100000000',2)) >> 8
                            b=(c2wTcpChatServerProtocol.Last_event_Id) & 255             
                            # Message_data
                            buf = struct.pack('!HBBBB',a,b,0x4,RoomId,User_ID)
                            c2wTcpChatServerProtocol.buf_logout += buf  #formation petit a petit du buf a envoyer dans le response event pour l'event logout
                            # Arret du timer
                            (self.callID).cancel()
                            userList=self.serverProxy.getUserList()
                        # Si l'utilisateur est dans un movie room
                        else:
                            Status_Code = 1
                        Response_Logout=struct.pack('!BHBHB',0x03,Seq_Number,0,1,Status_Code)
                        self.transport.write(Response_Logout)
                        self.response=Response_Logout
                        self.datagram=bytearray(0)

#----------------------------- RESPONSE_EVENTS -----------------------------------------------

                    if Message_Type == 0x06:
                        # Récupération du data
                        (LastEventId_a,LastEventId_b,Nbr_Events,Room_Id)=struct.unpack('!HBBB',self.datagram[6:6+Message_Length])
                        # Récupération du last_event_id de l'utilisateur
                        LastEventId = (LastEventId_a<<8)|LastEventId_b
                        # Initialisation du buffer qui va contenire la réponse du serveur
                        buf = bytearray(0)
                        event_nbr=0
                        v=0 # Position finale de l"event" dans le buffer
                        i=0 # Position initiale de l"event" dans le buffer
                        p=0 # Taille de l"event"

                        # Si l'utilisateur demande les événements d'un room précis
                        if Room_Id != 0: 
                         # Event : new message
                            while(i <= len(c2wTcpChatServerProtocol.buf_new_msg)-1): # Parcours du buffer contenant tous les nouveaux messages
                                taille_msg = struct.unpack('!H',c2wTcpChatServerProtocol.buf_new_msg[i+6:i+8]) # Détermination de la taille de chaque message
                                p = int(taille_msg[0]) + 8
                                v += p
                                # Si l'evenement s'est passé dans le room et si son event id est supérieur au last_event_id du client on le récupère
                                if (c2wTcpChatServerProtocol.buf_new_msg[i+4] == Room_Id) and ( ( (c2wTcpChatServerProtocol.buf_new_msg[i]<<16) | (c2wTcpChatServerProtocol.buf_new_msg[i+1]<<8) | c2wTcpChatServerProtocol.buf_new_msg[i+2]) > LastEventId):
                                    buf += c2wTcpChatServerProtocol.buf_new_msg[i:v]
                                    event_nbr+=1
                                i+=p
                        # Event : new user
                            v=0
                            i=0
                            p=0

                            while(i <= len(c2wTcpChatServerProtocol.buf_new_user)-1): # Parcours du buffer contenant tous les nouveaux utilisateurs
                                ul = c2wTcpChatServerProtocol.buf_new_user[i+6]
                                p = int(ul) + 7
                                v+=p
                                if (( (c2wTcpChatServerProtocol.buf_new_user[i]<<16) | (c2wTcpChatServerProtocol.buf_new_user[i+1]<<8) | c2wTcpChatServerProtocol.buf_new_user[i+2]) >LastEventId):
                                    buf += c2wTcpChatServerProtocol.buf_new_user[i:v]
                                    event_nbr+=1
                                i+=p
                        # Event : logout
                            p = 0
                            i = 0
                            v = 0

                            while(i <= len(c2wTcpChatServerProtocol.buf_logout)-1): # Parcours du buffer contenant tous les nouveaux logout
                                p = 6
                                v+=p
                                if (((c2wTcpChatServerProtocol.buf_logout[i]<<16) | (c2wTcpChatServerProtocol.buf_logout[i+1]<<8) | c2wTcpChatServerProtocol.buf_logout[i+2]) > LastEventId ):
                                    buf += c2wTcpChatServerProtocol.buf_logout[i:v]
                                    event_nbr+=1
                                i+=p
                        # Event : switch room
                            i=0
                            v=0
                            p=0
                            
                            while(i <= len(c2wTcpChatServerProtocol.buf_switch)-1):
                                p = 7
                                v+=p
                                if (c2wTcpChatServerProtocol.buf_switch[i+6] == Room_Id ) and (( (c2wTcpChatServerProtocol.buf_switch[i]<<16) | (c2wTcpChatServerProtocol.buf_switch[i+1]<<8) | c2wTcpChatServerProtocol.buf_switch[i+2]) > LastEventId):
                                    buf += c2wTcpChatServerProtocol.buf_switch[i:v]
                                    event_nbr+=1
                                if (c2wTcpChatServerProtocol.buf_switch[i+6] == 0 ) and (( (c2wTcpChatServerProtocol.buf_switch[i]<<16) | (c2wTcpChatServerProtocol.buf_switch[i+1]<<8) | c2wTcpChatServerProtocol.buf_switch[i+2]) > LastEventId):
                                    buf += c2wTcpChatServerProtocol.buf_switch[i:v]
                                    event_nbr+=1
                                i+=p
                            buf1 =struct.pack('!BHBHB',0x07,Seq_Number,0,len(buf)+1,event_nbr)
                            buf1 += buf
                            
                        # Si l'utilisateur demande tous les événements 
                        else:
                         # Event : new message
                            p = 0
                            i = 0

                            while(i <= len(c2wTcpChatServerProtocol.buf_new_msg)-1):
                                taille_msg = struct.unpack('!H',c2wTcpChatServerProtocol.buf_new_msg[i+6:i+8])
                                p = int(taille_msg[0]) + 8
                                v+=p
                                if ( ( (c2wTcpChatServerProtocol.buf_new_msg[i]<<16) | (c2wTcpChatServerProtocol.buf_new_msg[i+1]<<8) | c2wTcpChatServerProtocol.buf_new_msg[i+2]) > LastEventId):
                                    buf += c2wTcpChatServerProtocol.buf_new_msg[i:v]
                                i += p
                         # Event : new user
                            p = 0
                            i = 0
                            v=0
                            while(i <= len(c2wTcpChatServerProtocol.buf_new_user)-1):
                                ul = c2wTcpChatServerProtocol.buf_new_user[i+6]
                                p = int(ul) + 7
                                v+=p
                                if (( (c2wTcpChatServerProtocol.buf_new_user[i]<<16) | (c2wTcpChatServerProtocol.buf_new_user[i+1]<<8) | c2wTcpChatServerProtocol.buf_new_user[i+2]) > LastEventId):
                                    
                                    buf += c2wTcpChatServerProtocol.buf_new_user[i:v]
                                i += p
                         # Event : logout
                            p = 0
                            i = 0
                            v = 0

                            while(i <= len(c2wTcpChatServerProtocol.buf_logout)-1):
                                p = 6
                                v+=p
                                if (((c2wTcpChatServerProtocol.buf_logout[i]<<16) | (c2wTcpChatServerProtocol.buf_logout[i+1]<<8) | c2wTcpChatServerProtocol.buf_logout[i+2]) > LastEventId ):
                                    buf += c2wTcpChatServerProtocol.buf_logout[i:v]
                                i += p
                         # Event : switch room
                            p = 0
                            i = 0
                            v = 0

                            while(i <= len(c2wTcpChatServerProtocol.buf_switch)-1):
                                p = 7
                                v+=p
                                if (( (c2wTcpChatServerProtocol.buf_switch[i]<<16) | (c2wTcpChatServerProtocol.buf_switch[i+1]<<8) | c2wTcpChatServerProtocol.buf_switch[i+2] ) > LastEventId):
                                    buf += c2wTcpChatServerProtocol.buf_switch[i:v]
                                i += p
                            p = 0
                            i = 0


                            buf1 = struct.pack('!BHBHB',0x07,Seq_Number,0,len(buf)+1,Nbr_Events)
                            buf1 += buf

                        self.transport.write(buf1)
                        self.response=buf1
                        self.datagram=bytearray(0)
        pass
