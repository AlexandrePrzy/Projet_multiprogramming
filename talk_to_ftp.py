import os
from ftplib import FTP
from logger import Logger
import ftplib 


class TalkToFTP:
    def __init__(self, ftp_website):
        my_srv = ftp_website.split(",")
        self.host = my_srv[0]
        self.user = my_srv[1]
        self.password = my_srv[2]
        self.directory = my_srv[3]
        self.ftp = False

    def connect(self):
        self.ftp = FTP(self.host, self.user, self.password)

    def disconnect(self):
        self.ftp.quit()

    # def go_to(self, folder_path):
    #     self.ftp.cwd(folder_path)

    def create_folder(self, folder):
        ftp_folder = folder.replace('\\','/')
        Logger.log_debug(f"change {folder} to {ftp_folder}")
        try:
            self.ftp.mkd(ftp_folder)
        except ftplib.error_perm:
            Logger.log_info("Folder existed : " + ftp_folder)
        else:
            Logger.log_info("Folder created : " + ftp_folder)

    def remove_folder(self, folder):
        ftp_folder = folder.replace('\\','/')
        Logger.log_debug(f"change {folder} to {ftp_folder}")
        try:
            self.ftp.rmd(ftp_folder)
        except ftplib.error_perm:
            Logger.log_info("Folder not removed : " + ftp_folder)
        else:
            Logger.log_info("Folder removed : " + ftp_folder)

    def file_transfer(self, path, srv_path, file_name):
        ftp_srv_path = srv_path.replace('\\','/')
        Logger.log_debug(f"change {srv_path} to {ftp_srv_path}")

        with open(os.path.join(path, file_name), 'rb') as f:
            self.ftp.storbinary('STOR ' + ftp_srv_path, f)
            
        Logger.log_info("File created / updated : srv {0} file {1}".format(ftp_srv_path, file_name ))

    def remove_file(self, file):
        ftp_file = file.replace('\\','/')
        Logger.log_debug(f"change {file} to {ftp_file}")
        try:
          self.ftp.delete(ftp_file)
        except ftplib.error_perm:
            Logger.log_info("File not exists :" + ftp_file)
        else:
            Logger.log_info("File removed :" + ftp_file)

    def get_folder_content(self, path):
        ftp_path = path.replace('\\','/')
        Logger.log_debug(f"change {path} to {ftp_path}")
        new_list = []
        try:
            init_list = self.ftp.nlst(ftp_path)
        except ftplib.error_perm:
            Logger.log_info("Not file in : %s", ftp_path)
        else:
            for path in init_list:
                new_list.append(path.replace("\\", os.path.sep).replace("/", os.path.sep))
        return new_list

    def if_exist(self, element, list):
        return element in list


