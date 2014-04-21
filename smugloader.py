#!/usr/local/bin/python2.7
#-------------------------------------------------------------------------------
# Name:        smugmug_uploader.py
#
# Purpose:
# Started with code from Scott Moonon
# http://scottmoonen.com/2008/12/01/smugmug-uploader/
# and modified it to automatically create albums, upload entire
# directories, and not upload duplicate images.
#
# Script is provided as-is, no warranty
#
# Modification Log:
# Date          Version Comments
# -----------   ------- --------------------------------------------------------
# 05-may-2011   1.0.0   Baseline code, version 1.0.0
# 06-may-2011   1.0.1   Improved help comments
# 10-jun-2011   1.0.2   Sorted files when uploading a directory (Thanks Robin!)
# 23-jul-2011   1.0.3   Added in img count for upload progress. Cleaned up
#                       image display name when printing current upload image.
# 25-nov-2011   1.0.4   Added in mail notification.
# 17-dec-2011   1.0.5   Changed mail notification to include URL
#                       Changed testing of presence of _su cookie
# 07-jan-2011   1.0.6   Added in password lookup.  This was necessary to send
#                       email with the appropriate password in case the album
#                       already existed.
#                       Added in password reset on an existing Album with the
#                       same "-p" argument
# 31-may-2012   1.0.7   Fixed issue with -e option and splitting
# 06-jun-2012   1.0.7   Check for smugmug.cfg in homedir first, then local dir
#                       Modified/updated help documentation
# 29-oct-2012   1.0.8   Added more debugging issue to better report on error
#                       with upload servers & load balancers.
#                       Added in password query option.
#                       Updated help information.
# 02-nov-2012   1.0.9   Performance improvements
#-------------------------------------------------------------------------------
import sys, re, urllib, urllib2, urlparse, hashlib, traceback, os.path, getopt,ConfigParser,smtplib
import time, socket
 
try    : import json
except : import simplejson as json
 
try:
	 opts, args = getopt.getopt(sys.argv[1:], "p:e:t:h:q", ["password=","email=","template=","help=","query_password"])
except getopt.GetoptError, err:
	 print str(err)
	 sys.exit (2)
 
 
def help():
 print """
 Requires: Python 2.6 or greater.
 
 Set constants via  file "smugmug.cfg", a file that needs to be in 
 your home directory (""" + os.path.expanduser("~") + """) [preferred] , or the current directory. An example of that file is as follows:
 
 [SMUGMUG]
 email=user@domain.com
 password=itsasecret
 template_name = default
 album_password = default_album_password
 email_to = address1,address2,address3
 
 # Don't change below this line...
 apikey=O8LJpfiWKCqqUNbWYKKwE0O2F6vqJF2n
 api_version=1.2.2
 api_url=https://secure.smugmug.com/services/api/json/1.2.2/?
 upload_url=http://upload.smugmug.com
 
 Valid arguments are:
 
 -p, --password=
 -e, --email=
 -t, --template=
 -h, --help=
 -q, --query_password
 
 The variable "email_to" is intended for email notifications once the upload
 has completed.  It will also require "smtp_server=" if you need to specify
 a host other than localhost.
 
 I store all my photos in a base directory named "Categories" and under that
 the Category name in smugmug, followed by the directory_name (album_name).
 Categories/Family/Kids will upload into a gallery named "Kids" in the Category
 "Family".  The script will ensure we don't upload duplicate photos based
 on the file name in the gallery.  If the gallery doesn't exist, we will create
 it with the "album_password" in the config file or via the -p parameter at the
 command line.
 
 The files/directories can be any mix and match..some directories, some files,
 etc, but the same tempalte and password will be used.
 
 
 Usage:
 
 """ + os.path.basename(__file__) + """ -t (template name) -p (gallery password) directory_or_path/and/file/name
 
 ie:
 
 """ + os.path.basename(__file__) + """ -p just4family Categories/Family/Kids/
 
 will upload all AVI & JPG fieles in the Categories/Family/Kids/ directory into
 the gallery "Kids" in the Category "Family"
 
 """ + os.path.basename(__file__) + """ -p just4family Categories/Family/Kids/DSC_003.JPG  Categories/Family/Cousins/
 
 will upload just DSC_003.JPG in the Categories/Family/Kids/ directory
 and all the AVI/JPG files in Categories/Family/Cousins/
 
 On windows, it would be something more like:
 python.exe """ + os.path.basename(__file__) + """ Categories/Family/Kids/DSC_003.JPG
 
 """
 sys.exit()
 
 
 
 
def safe_geturl(request) :
 global su_cookie
 for x in range(5) :
	try :
		response_obj = urllib2.urlopen(request)
		addr = socket.gethostbyname(urlparse.urlparse(response_obj.geturl()).netloc)
		response = response_obj.read()
		result = json.loads(response)
		meta_info = response_obj.info()
		if meta_info.has_key('set-cookie') :
				match = re.search('(_su=\S+);', meta_info['set-cookie'])
				if match and match.group(1) != "_su=deleted" :
					su_cookie = match.group(1)
		if result['stat'] != 'ok':
				if x < 5 : 
					print '\t Error, result stat is: ' + result['stat']
					print '\t retry number: %i ' % (x)
					continue
				else:
					raise Exception('Bad result code')
		else:
				return result
	except urllib2.URLError, e :
		if str(e[0]) == '[Errno 32] Broken pipe':
			# Amazon web service is a flaky beast...retry several times
			# before giving up.
			pass
		if x < 4 :
			print "\t!!! failed !!! \n\tError: %s" % (str(e))
			return None
 
def smugmug_request(method, params) :
 global su_cookie
 
 paramstrings = [urllib.quote(key)+'='+urllib.quote(str(params[key])) for key in params]
 paramstrings += ['method=' + method]
 url = urlparse.urljoin(api_url, '?' + '&'.join(paramstrings))
 request = urllib2.Request(url)
 if su_cookie :
	request.add_header('Cookie', su_cookie)
 return safe_geturl(request)
 
def get_album_info ( album_name ):
			album_id = None
			album_key = None
			result = smugmug_request('smugmug.albums.get', {'SessionID' : session})
			for album in result['Albums'] :
							if album['Title'] == album_name :
											album_id = album['id']
											album_key = album['Key']
			return album_id , album_key
 
def get_album_password ( album_id , album_key):
			result = smugmug_request('smugmug.albums.getInfo', {'SessionID' : session, 'AlbumID' : album_id, 'AlbumKey' : album_key})
			#print result
			album_password = result['Album']['Password']
			#print album_password
			return album_password
 
def create_album ( session , album_name , album_category , album_template):
			result = smugmug_request('smugmug.albums.create',{'SessionID' : session,
																				 'Title'     : album_name,
																				 'CategoryID': get_category_id( session, album_category) ,
																				 'AlbumTemplateID' : album_template ,
																				 'Password' : album_password ,
																				 'Originals' : '1',
																				 'Filenames' : '1'})
			album_id = result['Album']['id']
			result = smugmug_request('smugmug.albums.changeSettings', {'SessionID' : session,
																																 'AlbumID' : album_id,
																																 'AlbumTemplateID' : int(album_template),
																																 'Password' : str(album_password),
																 'SortDirection' : 'True',
																 'SortMethod' : 'DateTimeOriginal',
																																 'Originals' : '1' })
 
def get_category_id ( session , album_category ):
			CATEGORY_ID = 0
			Categories =  smugmug_request('smugmug.categories.get',{'SessionID' : session})
			for key, value in dict.items(Categories):
							if key == 'Categories':
											for items in value:
												 if items['Name'] == album_category:
															CATEGORY_ID = items['id']
															break
			return CATEGORY_ID
 
def load_existing_image_array ( session , album_id , album_key ):
			imgArray =  smugmug_request('smugmug.images.get',{'SessionID' : session,
																							'AlbumID'   : album_id,
																							'AlbumKey'  : album_key,
																							'Heavy'     : 'True' })
			return imgArray
 
def does_image_exist (file, imgArray):
			fileExists = None
			# Remove the %20, etc. from the file name as it won't have this
			# from Smugmug since it uses urllib...ie, on disk file%20name.jpg
			# will show up on smugmug as file name.jpg, so to compare, we remove
			# the same
			file = urllib.unquote(file)
			if imgArray != None:
			 for key, value in dict.items(imgArray):
							if key == 'Album':
							 for a, b in dict.items(value):
								 if a == 'Images':
									for item in b:
											if item['FileName'] == file:
															fileExists = "True"
															break
			return fileExists
 
def get_template_id ( session , template_name ):
			template_id = int(2)
			templates =  smugmug_request('smugmug.albumtemplates.get',{'SessionID' : session})
			for key, value in dict.items(templates):
							if key == 'AlbumTemplates':
											for  item in (value):
															if item['AlbumTemplateName'] == template_name:
																template_id = item['id']
																break
			return template_id
 
def query_password( session ):
		print "-" * 74
		print "+ %-45s | %10s | %9s +" % ( "Title" , "Password" , "Public" )
		print "-" * 74
		my_albums = []
		update_albums = {}
		albums =  smugmug_request('smugmug.albums.get',{'SessionID' : session, 'Heavy' : 'True'})
		#print albums + '\n\n'
		for key, value in dict.items(albums):
				if key == 'Albums':
								for item in value:
										print "| %-45s | %10s | %9s |" % ( item['Title'] , item['Password'], item['Public'] )
		print "-" * 74
		print "Query Complete.  Exiting"
		sys.exit(0)
 
 
##############################################################
#                                                            #
# Main Logic                                                 #
#                                                            #
##############################################################
 
def main():
		failed_image_list = []
		albums_uploaded = []
		file_msg_log=[]
		imgcnt=0
		receivers=[]
		global template_name
		global album_password
		global su_cookie
		global api_url
		global session
		# Assume there is no pwd at the command line
		pwd_set = False
		# Read the config file for the variables we need.  See above for documentation
		#
		config = ConfigParser.RawConfigParser()
		cfgFile = os.path.expanduser("~")+'/smugmug.cfg'
		config.read([cfgFile,'smugmug.cfg'])
		email=config.get('SMUGMUG','email')
		password=config.get('SMUGMUG','password')
		apikey=config.get('SMUGMUG','apikey')
		api_version=config.get('SMUGMUG','api_version')
		api_url=config.get('SMUGMUG','api_url')
		upload_url=config.get('SMUGMUG','upload_url')
		template_name = config.get('SMUGMUG','template_name')
		album_password = config.get('SMUGMUG','album_password')
 
		try:
				receivers = config.get('SMUGMUG','email_to').replace(';',' ').replace(',',' ').split()
		except:
				receivers=[]
		try:
				smtp_server = config.get('SMUGMUG','smtp_server')
		except:
				smtp_server='localhost'
		 
		#Create the session
		su_cookie  = None
		print "Attempting to login to smugmug..."
		result_login = smugmug_request('smugmug.login.withPassword',
													 {'APIKey'       : apikey,
														'EmailAddress' : email,
														'Password'     : password})
		session = result_login['Login']['Session']['id']
		homepage = result_login['Login']['User']['URL']
		realname = result_login['Login']['User']['DisplayName']
 
		for opt, arg in opts:
		 if opt in ("-p", "--password"):
			pwd_set = True
			album_password = arg
		 elif opt in ("-e","--email"):
			receivers = str(arg).replace(';',' ').replace(',',' ').split()
		 elif opt in ("-t", "--template"):
			template_name = arg
		 elif opt in ("-h", "--help"):
			help()
		 elif opt in ("-q", "--query_password"):
			query_password( session )
 
		files = []
		if len(sys.argv) < 2 :
		 print 'Usage:'
		 print '  upload.py  Category/Album/File|Category/Album '
		 print
		 sys.exit(0)
 
		for arg in args:
			 # Determine if argv is a file or diretory.  If it's a directory, assign a list
			 # for the files.  If it's a directory/file combination, set accordingly.
			 if os.path.isdir(arg) == True:
							files = os.listdir(arg)
							files_prefix = arg.rstrip('/') + '/'
							files.sort(key=str.lower)
							album_name = os.path.basename(os.path.normpath(arg))
							album_category = os.path.basename(os.path.dirname(os.path.normpath(arg)))
			 elif os.path.isfile(arg) == True:
							files = [arg]
							files_prefix = ''
							album_name = os.path.basename(os.path.dirname(arg))
							album_category = os.path.basename(os.path.dirname(os.path.dirname(os.path.normpath(arg))))
			 else:
							print
							print "The argument passed in '%s' is not a file or directory." % (arg)
							print
							sys.exit(1)
 
 
 
 
 
			 # Get Album Information, create if necessary
			 album_id , album_key = get_album_info ( album_name )
			 if album_id is None :
				create_album( session , album_name , album_category, get_template_id( session , template_name ) )
				# Check for album now...
				album_id , album_key = get_album_info ( album_name )
				if album_id is None :
							print 'An error occurred with the album creation... exiting'
							sys.exit(1)
				imgArray = {}
			 else:
				imgArray = load_existing_image_array ( session , album_id , album_key )
				# Set new password if album already existed but a password was specified at the command line
				# However, don't reset unless the -p option is provided.  This will take care of anyone changing
				# via the website itself
				if pwd_set:
					 curAlbumPassword = get_album_password( album_id , album_key )
					 if curAlbumPassword != album_password:
							 result = smugmug_request('smugmug.albums.changeSettings',{'SessionID' : session,
																																				 'AlbumID' : album_id,
																																				 'Password' : str(album_password)})
 
 
			 # Display the message on where files will be uploaded to
			 albums_uploaded.append(urllib.quote(homepage + "/" + album_category + "/" + album_name,'://'))
			 msg = "+ Category/Album will be: %s/%s (%i) +" % (album_category,album_name,album_id)
			 print '\n%s%s' % ('+','+'.rjust(len(msg)-1,'-'))
			 print msg
			 print '+%s' % ('+'.rjust(len(msg)-1,'-'))
			 print
 
			 foo = int(0)
			 numOfFiles = len(files)
			 # For all files listed, upload them into the appropriate place
			 for file in (files):
 
				#Don't upload duplicate images:
				foo = foo + 1
				print "Processing %s (%i of %i)" % (file,foo,numOfFiles)
				if does_image_exist( os.path.basename(file) , imgArray) == None:
					 filename = files_prefix + file
					 if re.search('.JPG$|.AVI$|.JPEG$|.PNG$|.GIF$',filename,flags=re.IGNORECASE):
							try:
											data = open(filename, 'rb').read()
							except IOError as (errno, strerror):
											print "I/O error({0}): {1}".format(errno, strerror)
							except:
											print "Unexpected error:", sys.exc_info()[0]
											raise
							dl = float(len(data))
							print "\tSize: %.2f mb" % (dl/1024/1024)
							print '\tUploading: %s/%s/%s' % (album_category ,album_name, file)
							file_msg_log.append( 'Uploaded: %s/%s/%s (%.2f mb) ' % (album_category,album_name,file, (dl/1024/1024)))
							try: 
									upload_request = urllib2.Request(upload_url, data,
																				 {'Content-Length'  : int(dl),
																					'Content-MD5'     : hashlib.md5(data).hexdigest(),
																					'Content-Type'    : 'none',
																					'X-Smug-SessionID': session,
																					'X-Smug-Version'  : api_version,
																					'X-Smug-ResponseType' : 'JSON',
																					'X-Smug-AlbumID'  : album_id,
																					'X-Smug-FileName' : os.path.basename(filename) })
							except URLError, e:
									 print e.reason
							result = safe_geturl(upload_request)
							if result == None:
											print "\tThere was a problem with uploading your file. \n\tUpload aborted"
											failed_image_list.append(filename)
							elif result['stat'] == 'ok' :
											print "\tSuccessful"
											imgcnt=imgcnt+1
											time.sleep(1)
							else:
											print "\tErrors occurred"
											print "\t%s" %  (result)
											failed_image_list.append(filename)
					 else:
							print "\tSkipping file as it does not have a valid extension"
				else:
							print "\tSkipping %s as it already exists in that album" % (file)
							#ml = 'Skipped %s as it already existed.' % (file)
							file_msg_log.append( 'Skipped %s as it already existed.' % (file) )
 
		#album_password = get_album_password ( album_id , album_key )
		try:
				for recepient in receivers:
						recepient=recepient.strip(' ,') # remove spaces around email addresses
						print("Processing email to [%s]") % (recepient)
						if re.match("^[a-zA-Z0-9._%-]+@[a-zA-Z0-9._%-]+.[a-zA-Z]{2,6}$",recepient):
								message = "From: " + realname + "<" + email + ">\n"
								message = message + "To: " + recepient + "\n"
								message = message + "Subject: New photos uploaded to " + str(len(albums_uploaded)) + " album(s) @smugmug!\n"
								message = message + "Gallery/Album uploaded: " + ", ".join(map(str,albums_uploaded))  + "\n"
								message = message + "Album Password: " + str(album_password) + "\n"
								message = message + "Total images processed: " + str(imgcnt) + "\n"
								message = message + "Image Log: \n\n" + '\n'.join(file_msg_log)
 
								if len(failed_image_list) > 0:
										message = message + "\nFailed images: " + ",".join(map(str,failed_image_list)) + "\n"
 
								try:
										smtpObj = smtplib.SMTP(smtp_server)
										smtpObj.sendmail(email, recepient, message)
								except:
										print
										print "Error: unable to send email, SMTP server error."
										print "Did you specify 'smtp_server=' in smugmug.cfg?"
										print
						else:
								print("Receiver email not valid in smugmug.cfg or via command line, skipping email")
		except:
				print "Not sending email, not configured properly.  Check variables in smugmug.cfg"
 
		print 'Exiting.'
 
if __name__ == '__main__':
		main()
