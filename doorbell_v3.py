#!/usr/bin/env python2.7

from __future__ import print_function
import RPi.GPIO as GPIO
import time
import serial
import os
import ConfigParser
import logging
import datetime
import socket
import fcntl
import struct
import tailer
#from datetime import datetime
from uptime import uptime
from gsmmodem.modem import GsmModem
from gsmmodem.exceptions import InterruptedException
import sys
sys.path.append('~/')
import usb.core
import usb.util
import cpr
import psutil

# Define our Barcode Scanner Character Map

chrMap = {
    4:  'a',
    5:  'b',
    6:  'c',
    7:  'd',
    8:  'e',
    9:  'f',
    10: 'g',
    11: 'h',
    12: 'i',
    13: 'j',
    14: 'k',
    15: 'l',
    16: 'm',
    17: 'n',
    18: 'o',
    19: 'p',
    20: 'q',
    21: 'r',
    22: 's',
    23: 't',
    24: 'u',
    25: 'v',
    26: 'w',
    27: 'x',
    28: 'y',
    29: 'z',
    30: '1',
    31: '2',
    32: '3',
    33: '4',
    34: '5',
    35: '6',
    36: '7',
    37: '8',
    38: '9',
    39: '0',
    40: 'KEY_ENTER',
    41: 'KEY_ESCAPE',
    42: 'KEY_BACKSPACE',
    43: 'KEY_TAB',
    44: ' ',
    45: '-',
    46: '=',
    47: '[',
    48: ']',
    49: '\\',
    51: ';',
    52: '\'',
    53: '`',
    54: ',',
    55: '.',
    56: '/',
    57: 'KEY_CAPSLOCK'
}

shiftchrMap = {
    4:  'A',
    5:  'B',
    6:  'C',
    7:  'D',
    8:  'E',
    9:  'F',
    10: 'G',
    11: 'H',
    12: 'I',
    13: 'J',
    14: 'K',
    15: 'L',
    16: 'M',
    17: 'N',
    18: 'O',
    19: 'P',
    20: 'Q',
    21: 'R',
    22: 'S',
    23: 'T',
    24: 'U',
    25: 'V',
    26: 'W',
    27: 'X',
    28: 'Y',
    29: 'Z',
    30: '!',
    31: '@',
    32: '#',
    33: '$',
    34: '%',
    35: '^',
    36: '&',
    37: '*',
    38: '(',
    39: ')',
    40: 'KEY_ENTER',
    41: 'KEY_ESCAPE',
    42: 'KEY_BACKSPACE',
    43: 'KEY_TAB',
    44: ' ',
    45: '_',
    46: '+',
    47: '{',
    48: '}',
    49: '|',
    51: ':',
    52: '"',
    53: '~',
    54: '<',
    55: '>',
    56: '?',
    57: 'KEY_CAPSLOCK'
}

# Uncomment the following line to log
#logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)

# read config file
settingsfile = '/root/doorbell/doorbell.cfg'
config = ConfigParser.RawConfigParser()
config.read(settingsfile)

# parse config variables
print(u'Initializing config...')
rp_pin = config.getint('Setup', 'raspberry_pin')
led_pin = config.getint('Setup', 'led_pin')
port = config.get('Setup', 'serialport')
sim_pin = config.get('Setup', 'pin')
baudrate = config.getint('Setup', 'baudrate')
button_str = config.get('Setup', 'message')
send_sms_to = config.get('Receiver', 'number') # used in single mode
doorbell_number = config.get('Setup', 'doorbell_number')
logfile = config.get('Setup', 'log')
updatewithcall = config.getboolean('Setup', 'updatewithcall')
wifi_on = config.getboolean('Setup', 'wifi_default_on')
full_cpr = config.getboolean('Setup', 'full_cpr')
only_valid_cpr = config.getboolean('Setup', 'only_valid_cpr')
sendmode = config.get('Receiver', 'mode') #single or group
numbers = config.get('Receiver', 'numbers') #used in group mode
# Get barcode scanner vendor and product id - eg. CipherLab 1560H
vendorid = int(config.get('Setup', 'barcode_vendorid'),16)
productid = int(config.get('Setup', 'barcode_productid'),16)

# define variables
count = 0
modeswitch = 0
cpu_usage = 0
mem_usage = 0
datalist = []
group_sms_to = numbers.split(";")
print(u'Finished Initializing config...')

# functions
def get_ip_address(ifname):
  try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15])
    )[20:24])
  except:
    return('n/a')

def write_phonenumbers(phonelist):
  global configfile
  csv_string = ''
  for i in phonelist:
    csv_string += i + ';'
  csv_string = csv_string[:-1]
  if len(phonelist) == 1:
    config.set('Receiver', 'number', format(csv_string))
  config.set('Receiver', 'numbers', format(csv_string))
  with open(settingsfile, 'wb') as configfile:
    config.write(configfile)

#callback functions
def handleCall(call):
    global configfile, send_sms_to, modem
    print(u'{0} is calling...'.format(call.number))
    time.sleep(2.0)
    call.answer()
    time.sleep(1.0)    
    call.hangup()
    if updatewithcall:
       if call.number is not None:
          print(u'Update with call enabled - updating config and notifying')
          print(u'Replying to previous receiver...')
          modem.sendSms(send_sms_to, 'Telefonen AFMELDT for ringetryk af {0}'.format(call.number))
          config.set('Receiver', 'number', format(call.number))
          with open(settingsfile, 'wb') as configfile:
             config.write(configfile)
          send_sms_to = config.get('Receiver', 'number')
          modem.sendSms(send_sms_to, 'Denne telefon modtager nu SMS ved ringetryk')
          print(u'SMS sent. - new receiver')
    else:
       print(u'Update with call is not enabled, notifying caller by SMS')
       if call.number is not None:
          modem.sendSms(call.number, 'Du skal sende SMS med kommando')
    return

def handleSms(sms):
    global configfile, logfile, send_sms_to, modem, updatewithcall, wifi_on, mem_usage, cpu_usage, full_cpr, only_valid_cpr, sendmode, group_sms_to
    print(u'===== SMS message received =====\nFrom: {0}\nTime: {1}\nMessage: {2}\n================================'.format(sms.number, sms.time, sms.text))
    if sms.number.lower() in ['voicemail']:
      print(u'voicemail - do nothing')
      print(u'Clearing SMS memory')
      modem.deleteMultipleStoredSms()
    elif sms.text.lower() in ['wifion']:
      config.set('Setup', 'wifi_default_on', True)
      with open(settingsfile, 'wb') as configfile:
         config.write(configfile)
      wifi_on = True
      os.remove('/tmp/wifioff') if os.path.exists('/tmp/wifioff') else None
      sms.reply('WIFI is on')
      print(u'Wifi turned ON...')
      os.system('sudo /sbin/ifup wlan0')
      os.system('sudo /etc/init.d/hostapd restart')
    elif sms.text.lower() in ['wifioff']:
      config.set('Setup', 'wifi_default_on', False)
      with open(settingsfile, 'wb') as configfile:
         config.write(configfile)
      wifi_on = False
      os.mknod('/tmp/wifioff') if not os.path.exists('/tmp/wifioff') else None
      sms.reply('WIFI is off')
      print(u'Wifi turned OFF...')
      os.system('sudo /sbin/ifdown wlan0')
      os.system('sudo /etc/init.d/hostapd stop')
    elif sms.text.lower() in ['cprcheckon']:
      print(u'Update settings for CPR check: ON...')
      config.set('Setup', 'only_valid_cpr', True)
      with open(settingsfile, 'wb') as configfile:
         config.write(configfile)
      only_valid_cpr = True
      sms.reply('CPR check AKTIVERET')
    elif sms.text.lower() in ['cprcheckoff']:
      print(u'Update settings for CPR check: OFF...')
      config.set('Setup', 'only_valid_cpr', False)
      with open(settingsfile, 'wb') as configfile:
         config.write(configfile)
      only_valid_cpr = False
      sms.reply('CPR check er nu DE-AKTIVERET - alt kan scannes og sendes')
    elif sms.text.lower() in ['fullcpron']:
      print(u'Update settings for full CPR: ON...')
      config.set('Setup', 'full_cpr', True)
      with open(settingsfile, 'wb') as configfile:
         config.write(configfile)
      full_cpr = True
      sms.reply('Nu sendes hele CPR nummeret (lovligt?)')
    elif sms.text.lower() in ['fullcproff']:
      print(u'Update settings for CPR check: OFF...')
      config.set('Setup', 'full_cpr', False)
      with open(settingsfile, 'wb') as configfile:
         config.write(configfile)
      full_cpr = False
      sms.reply('Nu sendes kun 6 cifre fra CPR nummeret')
    elif sms.text.lower() in ['ringon']:
      print(u'Update settings by caller-id: ON...')
      config.set('Setup', 'updatewithcall', True)
      with open(settingsfile, 'wb') as configfile:
         config.write(configfile)
      updatewithcall = True
      sms.reply('Opdater boks med opkald AKTIVERET')
    elif sms.text.lower() in ['ringoff']:
      print(u'Update settings by caller-id: OFF...')
      config.set('Setup', 'updatewithcall', False)
      with open(settingsfile, 'wb') as configfile:
         config.write(configfile)
      updatewithcall = False
      sms.reply('Opdater boks med opkald DE-AKTIVERET')
    elif sms.text.lower() in ['skift','skift ']:
      if sendmode == "single":
        print(u'Replying to SMS...')
        modem.sendSms(send_sms_to, 'Telefonen AFMELDT for ringetryk af {0}'.format(sms.number))
        config.set('Receiver', 'number', format(sms.number))
        with open(settingsfile, 'wb') as configfile:
           config.write(configfile)
        send_sms_to = config.get('Receiver', 'number')
        sms.reply('Denne telefon modtager nu SMS ved ringetryk')
        print(u'SMS sent. - ny modtager')
      else:
        print(u'SMS-single modus ikke aktivt')
        sms.reply('SMS-single modus ikke aktivt')  
    elif sms.text.lower() in ['sysinfo','sysinfo ']:
      print(u'Replying to SMS...')
      ips=get_ip_address('lo')+', '+get_ip_address('eth0')+', '+get_ip_address('wlan0')+', '+get_ip_address('wwan0')
      m, s = divmod(uptime(), 60)
      h, m = divmod(m, 60)
      sysuptime = "%d:%02d:%02d" % (h, m, s)
      systime = time.strftime("%d-%m-%Y %H:%M:%S")
      cpu_usage = psutil.cpu_percent()
      mem_usage = psutil.phymem_usage().percent
      sms.reply('SYSINFO:\nSystime: {3}\nSignal: {0}\nUptime: {1}\nIP: {2}\nCPU usage: {4}%\nMEM usage: {5}%'.format(modem.signalStrength,sysuptime,ips,systime,cpu_usage,mem_usage))
      print(u'SMS 1/2 sent. - SYSINFO')
      sms.reply('SYSINFO:\nWifi-On: {0}\nRing-On: {1}\nFuldt CPR: {2}\nCheck CPR/scan: {3}\nSMS-mode: {4}'.format(wifi_on, updatewithcall, full_cpr, only_valid_cpr, sendmode))
      print(u'SMS 2/2 sent. - SYSINFO')
    elif sms.text.lower() in ['log']:
      print(u'Replying to SMS...')
      revlog=tailer.tail(open(logfile), 5)
      lines = [ x[:-2] for x in revlog ]
      taillog = '\n'.join(lines)
      taillog = taillog.replace(";"," ")
      sms.reply('Sidste 5 tryk:\n\n{0}'.format(taillog))
      print(u'SMS sent. - LOG - tail 5 lines')
    elif sms.text.lower() in ['status','status ']:
      print(u'Replying to SMS...')
      revlog=tailer.tail(open(logfile), 50)
      logcount=0
      for s in revlog:
         logcount = logcount + int(s.count(time.strftime("%d-%m-%Y")))
      recipient = ''
      if sendmode == "group":
        for i in group_sms_to:
          recipient += i + '\n'
      else:
        recipient = send_sms_to
      status_besked = 'STATUS-BESKED:\nmodtager er: {0}\nAntal tryk i dag: {1}'.format(recipient, logcount)
      cc = 0
      chunk = ''
      status_besked_lines = (i.strip() for i in status_besked.splitlines())
      for line in status_besked_lines:
        chunk += line + '\n'
        if len(chunk) > 120:
          cc += 1
          sms.reply(format(chunk))
          chunk = ''
          print(u'SMS {0} sent. - STATUS receiver'.format(cc))
      if len(chunk) > 0:
        cc += 1
        sms.reply(format(chunk))
        print(u'SMS {0} sent. - STATUS receiver'.format(cc))
    elif sms.text.lower() in ['rpi-tid']:
      print(u'set Raspberry Pi System time to {0}'.format(sms.time))
      os.system('date +"%Y-%m-%d %H:%M:%S%:z" -s "{0}"'.format(sms.time))
    elif sms.text.lower() in ['reboot']:
      print(u'Rebooting...')
      sms.reply('Genstarter...')
      if sendmode == 'group':
        for sms_number in group_sms_to:
          modem.sendSms(sms_number, 'Boksen genstartet af {0}'.format(sms.number))
          print(u'Sending SMS to {0}'.format(sms_number))
      else:
        modem.sendSms(send_sms_to, 'Boksen genstartet af {0}'.format(sms.number))
      os.system('sudo reboot')
    elif sms.text.lower() in ['poweroff']:
      print(u'Powering off...')
      sms.reply('Slukker boksen...')
      if sendmode == 'group':
        for sms_number in group_sms_to:
          modem.sendSms(sms_number, 'Boksen slukket af {0} - skal den vedblive med det?'.format(sms.number))
          print(u'Sending SMS to {0}'.format(sms_number))
      else:
         modem.sendSms(send_sms_to, 'Boksen slukket af {0} - skal den vedblive med det?'.format(sms.number))
      os.system('sudo poweroff')
    elif sms.text.lower() in ['changemode', 'changemode ']:
      if sendmode == "single" :
        sendmode = "group"
        sms.reply('Skifter fra SMS-single modus til SMS-gruppe modus')
      else:
        sendmode = "single"
        sms.reply('Skifter fra SMS-gruppe modus til SMS-single modus')
      config.set('Receiver', 'mode', sendmode)
      with open(settingsfile, 'wb') as configfile:
        config.write(configfile)
      print(u'Modus skiftet... Aktiv modus: {0}'.format(sendmode))
    elif sms.text.lower() in ['add', 'add ']:
      if sendmode == "group":
        if sms.number in group_sms_to:
          print(u'SMS gruppe fortsat: {0}'.format(group_sms_to))
          sms.reply('Dit nummer {0} er allerede modtager i SMS-gruppen'.format(sms.number))       
        else:
          group_sms_to.append(format(sms.number))
          write_phonenumbers(group_sms_to)
          print(u'SMS gruppe nu: {0}'.format(group_sms_to))
          sms.reply('Dit nummer {0} er nu modtager i SMS-gruppen'.format(sms.number))
      else:
        print(u'SMS-gruppe modus er ikke aktivt')
        sms.reply('SMS-gruppe modus er ikke aktivt') 
    elif sms.text.lower() in ['remove', 'remove ']:
      if sendmode == "group":
        if len(group_sms_to) > 1:
          if sms.number in group_sms_to: 
            group_sms_to.remove(format(sms.number))
            write_phonenumbers(group_sms_to)
            print(u'SMS gruppe nu: {0}'.format(group_sms_to))
            sms.reply('Dit nummer {0} er nu fjernet fra SMS-gruppen'.format(sms.number))
          else:
            print(u'SMS gruppe fortsat: {0}'.format(group_sms_to))
            sms.reply('Dit nummer kan ikke fjernes fra SMS-gruppen. {0} findes ikke.'.format(sms.number))
        else:
          print(u'Only one left - SMS gruppe fortsat: {0}'.format(group_sms_to))
          sms.reply('Der er kun een SMS-modtager tilbage i SMS-gruppen - sidste modtager kan ikke fjernes.')
      else:
        print(u'SMS-gruppe modus er ikke aktivt')
        sms.reply('SMS-gruppe modus er ikke aktivt')
    elif sms.text.lower() in ['cleanup', 'cleanup ']:
      if sendmode == 'group':
        for sms_number in group_sms_to:
          if sms_number != sms.number:
            modem.sendSms(sms_number, 'SMS-gruppen er nu nulstillet af {0} - Dit nummer {1} modtager ikke flere beskeder ved ringetryk.'.format(sms.number,sms_number))
            print(u'Sending SMS to {0}'.format(sms_number))
        group_sms_to = [sms.number]
        write_phonenumbers(group_sms_to)
        print(u'SMS gruppe - renset - nu: {0}'.format(group_sms_to))
        sms.reply('SMS-gruppen nulstillet - eneste modtager er nu {0} '.format(sms.number))
      else:
        print(u'SMS-gruppe modus er ikke aktivt')
        sms.reply('SMS-gruppe modus er ikke aktivt')
    elif sms.text.lower() in ['help', 'help ']:
      if sendmode == 'group':
        sms.reply('Mulig kommandoer: add, remove, cleanup, status, log')
      else:
        sms.reply('Mulig kommandoer: skift, status, log')
    else: 
      print(u'cmd unknown - Replying to SMS...')
      sms.reply('SMS modtaget med ukendt kommando: "{0}{1}"'.format(sms.text[:20], '...' if len(sms.text) > 20 else ''))
      print(u'SMS sent.')
    print(u'Clearing SMS memory')
    modem.deleteMultipleStoredSms()
    return

def doorbell(channel):
    global modem, count
    time.sleep(0.05)         # need to filter out the false positive of some power fluctuation
    if GPIO.input(rp_pin) == GPIO.HIGH:
      return
    GPIO.output(led_pin,False)
    count += 1
    print(u'{0} - Button pressed - SMS sent...'.format(datetime.datetime.strftime(datetime.datetime.now(), '%d-%m-%Y %H:%M:%S')))
    if sendmode == 'group':
      for sms_number in group_sms_to:
        modem.sendSms(sms_number, button_str)
        print(u'Sending SMS to {0}'.format(sms_number))
    else:
      modem.sendSms(send_sms_to, button_str)
    GPIO.output(led_pin,True)
    f = open(logfile,'a')
    f.write('{0};{1}\n'.format(datetime.datetime.strftime(datetime.datetime.now(), '%d-%m-%Y;%H:%M:%S'), count))
    f.close()
    return

def init_barcode(vendorid, productid):
  global device, endpoint
  # find our device by id
  device = usb.core.find(idVendor=vendorid, idProduct=productid)
  if device is None:
    print(u'Could not find Barcode Reader')
    return False

  # remove device from kernel, this should stop
  # reader from printing to screen and remove /dev/input
  if device.is_kernel_driver_active(0):
    try:
        device.detach_kernel_driver(0)
    except usb.core.USBError as e:
        print(u"Could not detatch kernel driver: %s" % str(e))
        return False

  # load our devices configuration
  try:
    device.set_configuration()
    device.reset()
  except usb.core.USBError as e:
    print(u"Could not set configuration: %s" % str(e))
    return False

  # get device endpoint information
  endpoint = device[0][(0,0)][0]
  return True

#wait for modem port, try modeswitch
print(u'Check modem port and wait...')
loop = 0
if not os.path.exists(port):
  print(u"Modem port not found... Trying  modeswitch...", end="")
while not os.path.exists(port):
  print('.', end="")
  if modeswitch == 0 :
     os.system('sudo usb_modeswitch -c /root/doorbell/usb_modeswitch.conf')
     modeswitch = 1
  time.sleep(1.0)
  loop += 1
  if loop > 10:
    break

#init modem
print('Initializing modem...')
modem = GsmModem(port, baudrate, incomingCallCallbackFunc=handleCall, smsReceivedCallbackFunc=handleSms)
modem.smsTextMode = True
modem.connect(sim_pin)
print(u'Now wait 5 sec more')
time.sleep(5.0)
print(u'GSM-modem Signal Strength: {0}'.format(modem.signalStrength))

#set system time form SMS
print(u'Setting RPi time with SMS to self')
modem.sendSms(doorbell_number, 'rpi-tid', deliveryTimeout=30)

#clearing sms storange
print(u'Clearing SMS memory')
modem.deleteMultipleStoredSms()

#init GPIO
print(u'Initializing GPIO...')
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(rp_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(led_pin, GPIO.OUT)
GPIO.add_event_detect(rp_pin, GPIO.FALLING, callback=doorbell, bouncetime=5000)

#check wifi status
print(u'Create Wifi-status file in /tmp ...')
if not wifi_on: 
   os.mknod('/tmp/wifioff') if not os.path.exists('/tmp/wifioff') else None
else:
   os.remove('/tmp/wifioff') if os.path.exists('/tmp/wifioff') else None

#wait
print(u'Now waiting... Ready for button to be pressed...')

#while True:
#remeber to add "break" if above loop is used

try:
  #GPIO
  GPIO.output(led_pin,True) # turn on led to show that i'm ready
  # init barcode-scanner
  print(u'Initializing barcode scanner')
  barcode_scanner_connected = init_barcode(vendorid,productid)
  while True:
    if not barcode_scanner_connected:
      break
    try:
      results = device.read(endpoint.bEndpointAddress, endpoint.wMaxPacketSize)
      datalist.append(results)
      if 40 in results:
        GPIO.output(led_pin,False)
        sendsmsbarcode = False
        # create a list of 8 bit bytes and remove
        # empty bytes
        ndata = []
        for d in datalist:
          if d.tolist() != [0, 0, 0, 0, 0, 0, 0, 0]:
            ndata.append(d.tolist())

        # parse over our bytes, check if valid cpr, and create string to final return
        sdata = ''
        for n in ndata:
          for nn in n: 
            if nn != 0:
              if nn > 3:
                if n[0] == 0: sdata +=chrMap[nn]
                elif n[0] == 2: sdata +=shiftchrMap[nn]
        sdata = sdata.replace("KEY_ENTER", "")
        if cpr.is_valid(sdata) and only_valid_cpr: 
          if not full_cpr: 
            bdate = sdata[0:6]
          else:
            bdate = sdata 
          print(u'{0} - Validt CPR scannet - sender SMS med ID: {1}'.format(datetime.datetime.strftime(datetime.datetime.now(), '%d-%m-%Y %H:%M:%S'),bdate))
          sendsmsbarcode = True 
        elif not only_valid_cpr:
          bdate = sdata
          print(u'{0} - DATA scannet - sender SMS med ID: {1}'.format(datetime.datetime.strftime(datetime.datetime.now(), '%d-%m-%Y %H:%M:%S'),bdate))
          sendsmsbarcode = True
        if sendsmsbarcode:
          count += 1
          if sendmode == 'group':
            for sms_number in group_sms_to:
              modem.sendSms(sms_number, button_str + " --- ID: " + bdate)
              print(u'Sending SMS to {0}'.format(sms_number))
          else:
            modem.sendSms(send_sms_to, button_str + " --- ID: " + bdate)
          f = open(logfile,'a')
          f.write('{0};{1}\n'.format(datetime.datetime.strftime(datetime.datetime.now(), '%d-%m-%Y;%H:%M:%S'), count))
          f.close()
        #reset datalist and device 
        datalist = []
        #usb.util.dispose_resources(device)
        #device.set_configuration()
        #device.reset()
        #endpoint = device[0][(0,0)][0] 
        GPIO.output(led_pin,True)
    except usb.core.USBError as e:
      results = None
      if e.args[1] == 'Operation timed out':
        continue # timeout means try again
      elif e.args[1] == 'No such device (it may have been disconnected)':
        print(u'Re-Initializing barcode scanner')
        init_barcode(vendorid,productid)
        continue
      else:
        #print(u"USB error: %s" % str(e.args[1])) #uncomment to see other usb errors e.g "Pipe error"
        continue # or alternate break              
  #modem
  print(u"No barcode reader looping...")
  modem.rxThread.join(2**31) # Specify a (huge) timeout so that it essentially blocks indefinitely, but still receives CTRL+C interrupt signal
except KeyboardInterrupt:
  modem.close()
  GPIO.cleanup()
  print(u'CTRL-C exit')
except: 
  modem.close()
  GPIO.cleanup()
  print(u'error')
finally:
  GPIO.cleanup()
  modem.close()
  print(u'clean exit')
