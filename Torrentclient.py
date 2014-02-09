#!/usr/bin/python3

import libtorrent as lt
import urllib.request
import threading
import time
import re
import json
import os
import traceback
import smtplib

LOG = 1
EMAIL_CONFIG = "email.conf.json"
REFRESH_INTERVAL = 10

def green(msg):
	return "\033[0;32m" + str(msg) + "\033[0;m"

def blue(msg):
	return "\033[0;34m" + str(msg) + "\033[0;m"

def yellow(msg):
	return "\033[0;33m" + str(msg) + "\033[0;m"

def red(msg):
	return "\033[0;31m" + str(msg) + "\033[0;m"


def log(msg):
	if LOG > 0:
		print(msg)

class Torrentclient(threading.Thread):

	def __init__(self, upload_limit=-1, download_limit=-1, status_mail=False):
		threading.Thread.__init__(self)
		if status_mail:
			self.status_mail = True
			try:
				email_config_file = open(EMAIL_CONFIG, "r")
				self.config = json.load(email_config_file)
				email_config_file.close()
				# check for necessary fields
				self.config["username"]
				self.config["password"]
				self.config["recipient"]
				log(green("Status mails successfully enabled"))
			except:
				log(yellow("Error while pasing email config, disabling status_mail"))
				self.status_mail = False
		self.files = dict()
		self.session = lt.session()
		self.session.listen_on(6881, 6891)
		self.torrent_dir = ".torrents"
		self.download_dir = "Downloads"
		self.do_things = True
		settings = self.session.settings()
		if upload_limit != -1:
			log(blue("Upload limit set to non-default value: " + str(upload_limit)))
		settings.upload_rate_limit = upload_limit
		if download_limit != -1:
			log(blue("Download limit set to non-default value: " + str(download_limit)))
		settings.download_rate_limit = download_limit
		self.session.set_settings(settings)

	def get_filename(self, urllib_response):
		filename = ""
		try:
			filename = re.sub(".*filename=\"", "", re.sub("\"$", "", dict(urllib_response.info())["Content-Disposition"]))
		except BaseException as e:
			log(yellow(traceback.format_exc()))
			log(yellow("Falling back to url as filename."))
			filename = re.findall("http[^\n]*", str(urllib_response.info()))[0]
		return filename
	def set_upload_limit(self, limit):
		settings = self.session.settings()
		settings.upload_rate_limit = limit
		self.session.set_settings(settings)
		log(yellow("Set upload limit to " + str(limit)))
		
	def set_download_limit(self, limit):
		settings = self.session.settings()
		settings.download_rate_limit = limit
		self.session.set_settings(settings)
		log(yellow("Set download limit to " + str(limit)))
	
	def add_torrent_by_file(self, filename):
		torrent_info = lt.torrent_info(filename)
		torrent_handle = self.session.add_torrent({"ti": torrent_info, "save_path": self.download_dir})
		torrent_handle.set_upload_limit(0)
		self.files[torrent_handle.name()] = filename
	
	def add_torrent(self, url):
		response = urllib.request.urlopen(url)
		filename = self.torrent_dir + "/" + self.get_filename(response)
		torrent = open(filename, "wb")
		torrent.write(response.read())
		torrent.close()
		self.add_torrent_by_file(filename)
		
	def send_mail(self, subject, text):
		gmail_user = self.config["username"]
		gmail_pwd = self.config["password"]
		FROM = self.config["username"]
		TO = [self.config["recipient"]] #must be a list

		# Prepare actual message
		message = """\From: %s\nTo: %s\nSubject: %s\n\n%s
		""" % (FROM, ", ".join(TO), subject, text)
		try:
			#server = smtplib.SMTP(SERVER) 
			server = smtplib.SMTP("smtp.gmail.com", 587) #or port 465 doesn't seem to work!
			server.ehlo()
			server.starttls()
			server.login(gmail_user, gmail_pwd)
			server.sendmail(FROM, TO, message)
			#server.quit()
			server.close()
			log(green("Successfully sent status mail!"))
		except BaseException as e:
			log(red(traceback.format_exc()))
	
	def deep_copy(self, elements):
		new_elements = []
		for element in elements:
			new_elements.append(element)
		return new_elements
	
	def kill(self):
		self.do_things = False
	
	def run(self):
		for torrent in os.listdir(self.torrent_dir):
			self.add_torrent_by_file(self.torrent_dir + "/" + torrent)
		while self.do_things:
			log(blue("Checking on torrents now..."))
			torrents = self.deep_copy(self.session.get_torrents())
			for torrent in torrents:
				log(green("Torrent: " + torrent.name() + " %.2f%% (%.1f kiB/s)" % (torrent.status().progress * 100, torrent.status().download_rate / 1024)))
				if torrent.is_paused():
					log(yellow("Torrent: " + torrent.name() + " was paused. Resumed."))
					torrent.resume()
				if torrent.is_seed():
					log(green("Torrent: " + torrent.name() + " is done. Removed."))
					if self.status_mail:
						self.send_mail("Torrent Complete!", "Torrent %s was completed!" % (torrent.name()))
					os.remove(self.files[torrent.name()])
					self.session.remove_torrent(torrent)
			time.sleep(REFRESH_INTERVAL)
