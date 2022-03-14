import logging
import os
import queue
import time
import threading
from tkinter import E
from unittest.util import sorted_list_difference
from Directory import Directory
from File import File
from talk_to_ftp import TalkToFTP


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


class DirectoryManager:
    def __init__(self, ftp_website, directory, depth,thread_nb, excluded_extensions):
        self.root_directory = directory
        self.depth = depth
        # list of the extensions to exclude during synchronization
        self.excluded_extensions = excluded_extensions
        # dictionary to remember the instance of File / Directory saved on the FTP
        self.synchronize_dict = {}
        self.os_separator_count = len(directory.split(os.path.sep))
        # list of the path explored for each synchronization
        self.paths_explored = []
        # list of the File / Directory to removed from the dictionary at the end
        # of the synchronization
        self.to_remove_from_dict = []
        
        #Threading

        #Command queue is where we store informations that will 
        #be read by thread of the thread pool
        self.command_queue=queue.Queue()
        #Folder dict is where we store information 
        #about the number of file left there is in a folder 
        self.folder_dict={} 
        #list containing all threads of the threadpool
        self.threadpool=[]
        self.threadlock=threading.Lock()
        #If user said that he wanted multiprocessing
        if(thread_nb>0):
            # if(thread_nb>6):
            #     thread_nb=6
            for i in range(thread_nb):
                tempThread=threading.Thread(target=self.multithread,args=(ftp_website,))
                tempThread.start()
                self.threadpool.append(tempThread)
        #If he didn't ask for it, we start only one thread
        else:
            tempThread=threading.Thread(target=self.multithread,args=(ftp_website,))
            tempThread.start()
            self.threadpool.append(tempThread)

        # FTP instance
        self.ftp = TalkToFTP(ftp_website)
        # create the directory on the FTP if not already existing
        self.ftp.connect()
        if self.ftp.directory.count(os.path.sep) == 0:
            # want to create folder at the root of the server
            directory_split = ""
        else:
            directory_split = self.ftp.directory.rsplit(os.path.sep, 1)[0]
        if not self.ftp.if_exist(self.ftp.directory, self.ftp.get_folder_content(directory_split)):
            self.command_queue.put(["add_folder",self.ftp.directory,""])
            
        self.ftp.disconnect()

    def synchronize_directory(self, frequency):
        while True:
            # init the path explored to an empty list before each synchronization
            self.paths_explored = []

            # init to an empty list for each synchronization
            self.to_remove_from_dict = []

            # search for an eventual updates of files in the root directory
            self.ftp.connect()
            self.search_updates(self.root_directory)
            
            # look for any removals of files / directories
            self.any_removals()
            
            self.ftp.disconnect()

            # wait before next synchronization
            time.sleep(frequency)
            

    def search_updates(self, directory):
        # scan recursively all files & directories in the root directory
        for path_file, dirs, files in os.walk(directory):

            for dir_name in dirs:
                folder_path = os.path.join(path_file, dir_name)

                # get depth of the current directory by the count of the os separator in a path
                # and compare it with the count of the root directory
                if self.is_superior_max_depth(folder_path) is False:
                    self.paths_explored.append(folder_path)

                    # a folder can't be updated, the only data we get is his creation time
                    # a folder get created during running time if not present in our list

                    if folder_path not in self.synchronize_dict.keys():
                        # directory created
                        # add it to dictionary
                        self.synchronize_dict[folder_path] = Directory(folder_path)

                        # create it on FTP server
                        split_path = folder_path.split(self.root_directory)
                        srv_full_path = '{}{}'.format(self.ftp.directory, split_path[1])
                        directory_split = srv_full_path.rsplit(os.path.sep,1)[0]
                        if not self.ftp.if_exist(srv_full_path, self.ftp.get_folder_content(directory_split)):
                            # add this directory to the FTP server
                            self.command_queue.put(["add_folder",srv_full_path,""])

            for file_name in files:
                file_path = os.path.join(path_file, file_name)

                # get depth of the current file by the count of the os separator in a path
                # and compare it with the count of the root directory
                if self.is_superior_max_depth(file_path) is False and \
                        (self.contain_excluded_extensions(file_path) is False):

                    self.paths_explored.append(file_path)
                    # try if already in the dictionary
                    if file_path in self.synchronize_dict.keys():

                        # if yes and he get updated, we update this file on the FTP server
                        if self.synchronize_dict[file_path].update_instance() == 1:
                            # file get updates
                            split_path = file_path.split(self.root_directory)
                            srv_full_path = '{}{}'.format(self.ftp.directory, split_path[1])
                            
                            self.command_queue.put(["delete_file",srv_full_path,""])
                            # update this file on the FTP server
                            
                            self.command_queue.put(["transfer_file",path_file,srv_full_path,file_name])

                    else:

                        # file get created
                        self.synchronize_dict[file_path] = File(file_path)
                        split_path = file_path.split(self.root_directory)
                        srv_full_path = '{}{}'.format(self.ftp.directory, split_path[1])
                        # add this file on the FTP server
                        self.command_queue.put(["transfer_file",path_file,srv_full_path,file_name])

    def any_removals(self):
        # if the length of the files & folders to synchronize == number of path explored
        # no file / folder got removed
        if len(self.synchronize_dict.keys()) == len(self.paths_explored):
            return

        # get the list of the files & folders removed
        path_removed_list = [key for key in self.synchronize_dict.keys() if key not in self.paths_explored]

        for removed_path in path_removed_list:
            # check if the current path is not in the list of path already deleted
            # indeed we can't modify path_removed_list now because we're iterating over it
            if removed_path not in self.to_remove_from_dict:
                # get the instance of the files / folders deleted
                # then use the appropriate methods to remove it from the FTP server
                if isinstance(self.synchronize_dict[removed_path], File):
                    split_path = removed_path.split(self.root_directory)
                    srv_full_path = '{}{}'.format(self.ftp.directory, split_path[1])
                    
                    self.command_queue.put(["delete_file",srv_full_path,""])
                    self.to_remove_from_dict.append(removed_path)

                elif isinstance(self.synchronize_dict[removed_path], Directory):
                    split_path = removed_path.split(self.root_directory)
                    srv_full_path = '{}{}'.format(self.ftp.directory, split_path[1])
                    
                    
                    self.to_remove_from_dict.append(removed_path)
                    # if it's a directory, we need to delete all the files and directories he contains
                    self.remove_all_in_directory(removed_path, srv_full_path, path_removed_list)

        # all the files / folders deleted in the local directory need to be deleted
        # from the dictionary use to synchronize
        for to_remove in self.to_remove_from_dict:
            if to_remove in self.synchronize_dict.keys():
                del self.synchronize_dict[to_remove]

    def remove_all_in_directory(self, removed_directory, srv_full_path, path_removed_list):
        directory_containers = {}
        
        for path in path_removed_list:

            # path string contains removed_directory and this path did not get already deleted
            if removed_directory != path and removed_directory in path \
                    and path not in self.to_remove_from_dict:

                # if no path associated to the current depth we init it
                if len(path.split(os.path.sep)) not in directory_containers.keys():
                    directory_containers[len(path.split(os.path.sep))] = [path]
                else:
                    # if some paths are already associated to the current depth
                    # we only append the current path
                    directory_containers[len(path.split(os.path.sep))].append(path)

        # sort the path depending on the file depth
        sorted_containers = sorted(directory_containers.values())
        #print(srv_full_path,sorted_containers)
        self.folder_dict.update({srv_full_path:0})
        
        # we iterate starting from the innermost file
        for i in range(len(sorted_containers)-1, -1, -1):
            for to_delete in sorted_containers[i]:
                to_delete_ftp = "{0}{1}{2}".format(self.ftp.directory, os.path.sep, to_delete.split(self.root_directory)[1])
                if isinstance(self.synchronize_dict[to_delete], File):
                    
                    self.command_queue.put(["delete_file",to_delete_ftp,srv_full_path])
                    self.to_remove_from_dict.append(to_delete)
                    self.threadlock.acquire()
                    self.folder_dict.update({srv_full_path:self.folder_dict.get(srv_full_path)+1})
                    self.threadlock.release()
                else:
                    # if it's again a directory, we delete all his containers also
                    self.remove_all_in_directory(to_delete, to_delete_ftp, path_removed_list)
        # once all the containers of the directory got removed
        # we can delete the directory also
    
        #print(srv_full_path,len(sorted_containers[len(sorted_containers)-1]))
        

        self.command_queue.put(["delete_folder",srv_full_path])
        self.to_remove_from_dict.append(removed_directory)
    # subtract current number of os separator to the number of os separator for the root directory
    # if it's superior to the max depth, we do nothing
    def is_superior_max_depth(self, path):
        if (len(path.split(os.path.sep)) - self.os_separator_count) <= self.depth:
            return False
        else:
            return True

    # check if the file contains a prohibited extensions
    def contain_excluded_extensions(self, file):
        extension = file.split(".")[1]
        if ".{0}".format(extension) in self.excluded_extensions:
            return True
        else:
            return False
    def multithread(self,ftp_website):
        ftp = TalkToFTP(ftp_website)

        while True:
            
            #If there is command in the queue
            if (self.command_queue.not_empty):
                #create a connection to the ftp server
                ftp.connect()
                #get an element from the queue
                command=self.command_queue.get()
                #The type of command tab is stored in the first index,  
                #other index are useful to store parameters
                if(command[0]=="delete_file"):
                    #If the second parameter is different from "" 
                    #and the key is not yet created 
                    #in the dictionnary , wait
                    if command[2]!="":
                        while(True):
                            self.threadlock.acquire()
                            if(not command[2] in self.folder_dict.keys()):
                                self.threadlock.release()
                                
                            else:
                                self.threadlock.release()
                                break
                            
                    #If the first parameter is not equal to ""
                    if(command[1]!=""):
                        #We delete the file in the remote server folder
                        ftp.remove_file(command[1])
                        #And we decrease the number of file left in the remote folder
                        self.threadlock.acquire()
                        if(command[2] in self.folder_dict.keys()):
                
                            self.folder_dict.update({command[2]:self.folder_dict.get(command[2])-1})
                        self.threadlock.release()
                elif(command[0]=="transfer_file"):
                    #If we want to transfer a file just use the command
                    ftp.file_transfer(command[1], command[2], command[3])
                

                elif(command[0]=="delete_folder"):
                    #Create a new key with the path of the folder 
                    #and the number of files in it as values
                    
                    
                    if(command[1] in self.folder_dict.keys()):
                        #Wait for all the folder to be deleted
                        while(True):
                            self.threadlock.acquire()
                            if(self.folder_dict.get(command[1])<=0):
                                self.threadlock.release()
                                break 
                            else:
                                #print(command[1],self.folder_dict.get(command[1]))
                                self.threadlock.release()
                        print("Sending delete to ftp")
                        #Once the remote folder is empty, remove it
                        ftp.remove_folder(command[1])
                        #Pop the folder from the map 
                        #because we're done removing it
                        self.folder_dict.pop(command[1])
                  
                elif(command[0]=="add_folder"):
                    #If we want to add a folder do it on the remote ftp
                    ftp.create_folder(command[1])
                ftp.disconnect()

