#!/usr/bin/env python
"""
Python script to Monitor NetApp SnapMirror Information
"""

# SSH must be setup on NetApp filers for Key Authentication
# https://practical-admin.com/blog/ssh-to-clustered-data-ontap-using-key-authentication/
#  security login create -user-or-group-name snapvault -vserver sg200-ntap-svm -application ssh -authentication-method publickey -role vsadmin-backup
#  security login publickey create -vserver sg200-ntap-svm -username snapvault -index 0 -publickey "ssh-rsa contents_of_public_key_here="


import argparse, textwrap, fnmatch, datetime
import xml.etree.cElementTree as ElementTree
import subprocess

# Import Brandt Common Utilities
import sys, os
sys.path.append( os.path.realpath( os.path.join( os.path.dirname(__file__), "/opt/brandt/common" ) ) )
import brandt

sys.path.pop()

version = 0.3
args = {}
args['cluster'] = True
args['test'] = False
args['output'] = 'text'
args['encoding'] = 'utf-8'
args['hosts'] = []

class customUsageVersion(argparse.Action):
  def __init__(self, option_strings, dest, **kwargs):
    self.__version = str(kwargs.get('version', ''))
    self.__prog = str(kwargs.get('prog', os.path.basename(__file__)))
    self.__row = min(int(kwargs.get('max', 80)), brandt.getTerminalSize()[0])
    self.__exit = int(kwargs.get('exit', 0))
    super(customUsageVersion, self).__init__(option_strings, dest, nargs=0)
  def __call__(self, parser, namespace, values, option_string=None):
    # print('%r %r %r' % (namespace, values, option_string))
    if self.__version:
      print self.__prog + " " + self.__version
      print "Copyright (C) 2013 Free Software Foundation, Inc."
      print "License GPLv3+: GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>."
      version  = "This program is free software: you can redistribute it and/or modify "
      version += "it under the terms of the GNU General Public License as published by "
      version += "the Free Software Foundation, either version 3 of the License, or "
      version += "(at your option) any later version."
      print textwrap.fill(version, self.__row)
      version  = "This program is distributed in the hope that it will be useful, "
      version += "but WITHOUT ANY WARRANTY; without even the implied warranty of "
      version += "MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the "
      version += "GNU General Public License for more details."
      print textwrap.fill(version, self.__row)
      print "\nWritten by Bob Brandt <projects@brandt.ie>."
    else:
      print "Usage: " + self.__prog + " [options] [hosts]"
      print "Script o Monitor NetApp SnapMirror Information.\n"
      print "Options:"
      options = []
      options.append(("-h, --help",            "Show this help message and exit"))
      options.append(("-v, --version",         "Show program's version number and exit"))
      options.append(("-o, --output OUTPUT",   "Type of output {text | csv | xml}"))
      options.append(("-c, --cluster",         "Operate in Cluster-mode"))
      options.append(("-7, --7mode",           "Operate in 7-mode (DFM)"))
      options.append(("-t, --test",            "Test SSH access to the hosts"))
      options.append(("hosts",                 "List of hosts."))
      length = max( [ len(option[0]) for option in options ] )
      for option in options:
        description = textwrap.wrap(option[1], (self.__row - length - 5))
        print "  " + option[0].ljust(length) + "   " + description[0]
      for n in range(1,len(description)): print " " * (length + 5) + description[n]
    exit(self.__exit)
def command_line_args():
  global args, version
  parser = argparse.ArgumentParser(add_help=False)
  parser.add_argument('-v', '--version', action=customUsageVersion, version=version, max=80)
  parser.add_argument('-h', '--help', action=customUsageVersion)
  parser.add_argument('-o', '--output',
          required=False,
          default=args['output'],
          choices=['text', 'csv', 'xml'],
          help="Display output type.")
  parser.add_argument('-c', '--cluster',
          action='store_true',
          default=args['cluster'],
          required=False,
          dest='cluster',
          help="Operate in Cluster-mode")
  parser.add_argument('-7', '--7mode',
          action='store_false',
          default=args['cluster'],          
          required=False,
          dest='cluster',
          help="Operate in 7-mode (DFM)")
  parser.add_argument('-t', '--test',
          action='store_true',    
          required=False,
          help="Test SSH access to the hosts")  
  parser.add_argument('hosts',
          nargs='*',
          default= args['hosts'],
          action='store',
          help="List of hosts.")
  args.update(vars(parser.parse_args()))


def test_hosts(hosts):
  print "Host\t\tPing\tSSH"
  failed=[]
  for host in hosts:
    _cmd = '/bin/ping -c 1 ' + str(host)
    p = subprocess.Popen([ _cmd ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    out, err = p.communicate()
    pingable = (p.returncode == 0)
    sshable = False

    if pingable:
      _cmd = "ssh -l snapvault " + str(host) + ' "version"'
      p = subprocess.Popen([ _cmd ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
      out, err = p.communicate()
      sshable = (p.returncode == 0)
    print str(host) + "\t" + str(pingable) + "\t" +str(sshable)

    if not pingable or not sshable: failed.append(host)

    if failed:
      _cmd = 'cat "$HOME/.ssh/id_rsa.pub"'
      p = subprocess.Popen([ _cmd ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
      out, err = p.communicate()
      if p.returncode != 0:
        sys.stderr.write( "Unable to find SSH PublicKey (~/.ssh/id_rsa.pub)!\n" )
        sys.exit(1)
      _publickey = " ".join(out.split(" ")[:2])
      for fail in failed:
        print "\nHost " + str(fail) + " failed! Be sure to:"
        print "Verify you can run the command: ssh -l snapvault " + str(fail) + ' "version"'
        print "On the host, run the commands:"
        print str(fail) + "::> security login create -user-or-group-name snapvault -vserver " + str(fail) + " -application ssh -authentication-method publickey -role vsadmin-backup"
        print str(fail) + '::> security login publickey create -vserver ' + str(fail) + ' -username snapvault -index 0 -publickey "' + str(_publickey) + '"'
        print

  return len(failed)

def cmode_get_snapmirror_status(host):
  _volumes = {}

  _cmd = 'ssh -l snapvault ' + str(host) + ' "rows 0; snapmirror show -fields source-path,type,destination-path,state,status,lag-time"'
  p = subprocess.Popen([ _cmd ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
  out, err = p.communicate()
  if p.returncode == 0:
    data = [ x.split() for x in out.split("\n") if x.strip() and x[0].isalpha()]
    header = data[0]
    for line in data[1:]:
      tmp = {}
      for x in range(len(header)):
        tmp[header[x]] = line[x]
      if tmp['type'] in ["DP","XDP"]:
        lagtime = str(tmp['lag-time']).split(":")
        if len(lagtime) > 1:
          lagtime = ['0','0','0','0'][len(lagtime):] + lagtime
          lagtime = [ int(x) for x in lagtime ]
          tmp['lag-time'] = datetime.datetime.now() - datetime.timedelta(days=lagtime[0], hours=lagtime[1], minutes=lagtime[2], seconds=lagtime[3])
        _volumes[tmp['source-path'].split(":")[1]] = tmp

    snapshots = ["daily","weekly","monthly"]
    for volume in _volumes:
      destvolume = _volumes[volume]["destination-path"].split(":")[1]
      _cmd = 'ssh -l snapvault ' + str(host) + ' "rows 0; snapshot show -volume ' + str(destvolume) + ' -fields snapshot,create-time,snapmirror-label"'
      p = subprocess.Popen([ _cmd ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
      out, err = p.communicate()
      if p.returncode == 0:
        data = [ x.split() for x in out.split("\n") if x.strip() and x[0].isalpha()]
        header = data[0]
        for line in data[1:]:
          tmp = {}
          for x in range(len(header)):
            if header[x] == "snapshot": tmp["snapshot"] = line[x]
            if header[x] == "create-time": tmp["create-time"] = " ".join(line[x:x+5])
            if header[x] == "snapmirror-label": tmp["snapmirror-label"] = line[-1]
          tmp["create-time"] = datetime.datetime.strptime(tmp["create-time"], '%a %b %d %H:%M:%S %Y')

          for snapshot in snapshots:
            if snapshot in str(tmp["snapshot"]).lower():
              if not _volumes[volume].has_key(snapshot):
                _volumes[volume][snapshot] = {}
                _volumes[volume][snapshot]["newest"] = tmp
                _volumes[volume][snapshot]["oldest"] = tmp
              else:
                if _volumes[volume][snapshot]["newest"]["create-time"] < tmp["create-time"]:
                  _volumes[volume][snapshot]["newest"] = tmp
                if _volumes[volume][snapshot]["oldest"]["create-time"] > tmp["create-time"]:
                  _volumes[volume][snapshot]["oldest"] = tmp

  return _volumes


# Start program
if __name__ == "__main__":
  command_line_args()

  if not args['hosts']:
    sys.stderr.write( "You failed to include a host!\n" )
    sys.exit(1)

  if args['test']: sys.exit( test_hosts(args['hosts']) )

  if args['cluster']:
    for host in args['hosts']:
      sm_data = cmode_get_snapmirror_status(host)
      for line in sm_data:
        print line, sm_data[line]
  else:
    for host in args['hosts']:
      print "DFM Host: " + str(host)
