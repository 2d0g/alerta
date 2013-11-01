#!/usr/bin/env python

"""Alerta WatchDog script to monitor Alerta service"""
__author__ = "Mark Bradley (mbrad@github)"
__version__ = "0.8"

import urllib, urllib2, sys, os, smtplib, time, socket
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Monitor options
alertaURL = 'http://alerta.example.com:8080/alerta/management/healthcheck'
httptimeout = 5
tko = 3
retrytime = 10
checkperiod = 600
# Email Options
fromaddr = 'Alerta Watchdog <alerta@example.com>'
toaddr = ['admins@example.com']
smtphost = 'localhost'
# PushOver.net Options
pushenable = False
pushurl = 'https://api.pushover.net/1/messages.json'
pushtoken = 'obtain-app-token-from-pushover'
pushuser = 'this-is-your-pushover-token'

class Event:
	"Event class to construct an event object"
	def __init__(self):
		self.epoch = int(time.time())
		tt = time.gmtime(self.epoch)
		self.human = '%02d/%02d/%02d %02d:%02d:%02d' % \
		(tt[2], tt[1], tt[0], tt[3], tt[4], tt[5])
		try:	
			request = urllib2.Request(alertaURL, None, { 'User-Agent' : 'python' })
			socket.setdefaulttimeout(httptimeout)
			httpresponse = urllib2.urlopen(request, None, timeout = httptimeout)
			self.code = httpresponse.getcode()
			self.body = httpresponse.read()
			httpresponse.close()
		except urllib2.HTTPError, e:
			self.code = e.code
			self.body = e.read()
		except urllib2.URLError, e:
			self.code = 0
			self.body = str(e.reason)
		except socket.timeout, e:
			self.code = 0
			self.body = str(e.reason)
		
def _argvchk():
	if len(sys.argv) == 1:
		return True
	elif ('-h' or '--help') in sys.argv[1]:
		print "\nThis daemon polls Alerta's Management URI remotely and determines if there is a problem.\n\t\
		Usage: %s (-f = foreground)\n" % ((sys.argv[0]).split('/')[-1])
		sys.exit(0)
	elif '-f' in sys.argv[1]:
		print "Debug Mode: Staying in foreground...\n"
		return False
	else:
		print >>sys.stderr, "Error: Unknown Option"
		sys.exit(1)

def dprint(msg):
	if isdaemon == False: print msg

def mailalert(last, cache, typestr):
	if pushcount > 3:
		dprint('Info: Not sending Email notification - too many messages for event')
		return
	elif pushcount == 3:
		suppnote = 'Further notifications will be suppressed.'
	else:
		suppnote = ' '
	msg = MIMEMultipart('alternative')
	msg['Subject'] = "Alerta Service Notification"
	msg['From'] = fromaddr
	msg['To'] = ', '.join(toaddr)
	if typestr == 'WARNING':
		colour = 'ff8c00'
	elif typestr == 'CRITICAL':
		colour = 'ff0000'
	elif typestr == 'OK':
		colour = '00ff00'
	text = """\
	Alerta state change: %s - Response: %s (Code: %d)

	TKO: %d
	Soft Event logged at %s
	Hard Event logged at %s

	Service Probed: %s

	%s

	Auto-generated by Alerta-WatchDog

	--

	""" % (typestr, last.body, last.code, tko, cache.human, \
		last.human, alertaURL, suppnote)
	html = """\
	<html>
	<head></head>
	<body>
	 <p>
	 Alerta state change: <span style="background-color:#%s;">%s</span> - Response: <b>%s</b> (Code: %d)<br />
	 <br />
	 <I>TKO</I>: %d<br />
	 &nbsp;&nbsp; &nbsp;<I>Soft Event triggered at</I> %s<br />
	 &nbsp;&nbsp; &nbsp;<I>Hard Event triggered at</I> %s<br />
	 <br />
	 &nbsp;&nbsp; &nbsp;<I>Service Probed:</I> %s</p>
	 <p><I><B>%s</I></B></p>
	 <p><I>Auto-generated by Alerta-WatchDog</I><p>
	 --
	</body>
	</html>
	""" % (colour, typestr, last.body, last.code, tko, cache.human, \
		last.human, alertaURL, suppnote)

	textpart = MIMEText(text, 'plain')
	htmlpart = MIMEText(html, 'html')
	msg.attach(textpart)
	msg.attach(htmlpart)

	s=smtplib.SMTP(smtphost)
	s.sendmail(fromaddr, toaddr, msg.as_string())

	dprint('\033[92mMAIL SENT\033[0m\n' + text)

def pushover(last, typestr):
	if pushcount > 3:
		dprint('Info: Not sending PushOver notification - too many messages for event')
		return
	elif pushenable == False:
		dprint('Info: PushOver notifications disabled.')
		return
	pushmessage = 'State: %s Response: %s (%s)' % (typestr, last.body, last.code)
	pushdata = urllib.urlencode({"token": pushtoken, "user": pushuser, "message": pushmessage})
	try:	
		pushrequest = urllib2.Request(pushurl, pushdata, { "Content-type": "application/x-www-form-urlencoded" })
		socket.setdefaulttimeout(httptimeout)
		pushresponse = urllib2.urlopen(pushrequest, timeout = httptimeout)
	except:
		dprint('Error: Could not send data to Pushover')
		
def main():
	"""Looping main function"""
	global pushcount
	pushcount = 1
	count = 1
	state = 'OK'
	sleeptime = checkperiod
	while 1:
		dprint('Probing Alerta URI: %s' % (alertaURL))
		response = Event()
		dprint('Probe Response: [ Code: %s | Body: %s | Epoch: %d ]' % \
		(response.code, response.body, response.epoch))
		dprint('\nCOUNT: %d' % (count))
		if response.code != 200:
			dprint('Event Triggered')
			if count == 1:
				cache = response
				dprint('Caching first event: [ Code: %d | Body: %s | Epoch: %d ]' % \
					(cache.code, cache.body, cache.epoch))
			if count == tko:
				#Warnings
				if response.body ==\
				 'HEARTBEAT_STALE':
					state = 'WARNING'
					dprint('State: \033[93mWARNING\033[0m')
					mailalert(response, cache, state)
					pushover(response, state)
					pushcount += 1
					count = 0 # Reset for tko more tries.
					sleeptime = checkperiod
					dprint('\nRe-Probing in %d seconds...' % (sleeptime))
					time.sleep(sleeptime)
					continue
				else:
				#Criticals
					state = 'CRITICAL'
					dprint('State: \033[91mCRITICAL\033[0m')
					mailalert(response, cache, state)
					pushover(response, state)
					pushcount += 1
					count = 0 # Reset for tko more tries.
					sleeptime = checkperiod
					dprint('\nRe-Probing in %d seconds...' % (sleeptime))
					time.sleep(sleeptime)
					continue
			count += 1
			sleeptime = retrytime
		elif response.code == 200:
			dprint('State: \033[92mOK\033[0m')
			if state != 'OK':
				state = 'OK'
				pushcount = 0
				mailalert(response, cache, state)
				pushover(response, state)
			sleeptime = checkperiod
			count = 1
		dprint('\nRe-Probing in %d seconds...' % (sleeptime))
		time.sleep(sleeptime)

if __name__ == '__main__':
	isdaemon = _argvchk()
	if isdaemon == True:
		pid = os.fork()
		if pid:
			sys.exit(0)
		else:
			print 'Alerta WatchDog process started... (PID: %d)' % (os.getpid()) 
			os.close(2)
			os.close(0)
			os.close(1)
			main()
			sys.exit(0)
	else:
		print 'PID: %d' % (os.getpid())
		main()

# vim: set ts=4 sw=4 et :
