#!/usr/bin/python
# wogri@google.com

# Copyright 2014 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This is not an official Google product.

"""A script to go through dovecot mailboxes and snooze mails until a given time.

Works like this: You need to have a predefined set of folders (see below how to
subscribe your user to those folders), and this script will go through the
folders every minute (so you have to set up a cron-job) and put an IMAP label
on them. The label will be called something like "MoveAt123456789" where the
number is the timestamp when the mail should be moved back into the users
inbox. So when you drag a mail into one of these folders it will stay there
until the MoveAt Timestamp has been reached, and then the script will remove
the IMAP label and move the mail back into the user's inbox and mark as new.
Run the script from cron every minute like this:
./dovecot-snooze.py user1 user2 user3

Add -h for help.
By the way, we assume that the separator of your Snooze folder is a dot, not a
slash. Unfortunately you can't change that currently. Send me a patch to fix
this!

to subscribe a new user:
$ user=maryjane
doveadm mailbox create -s -u $user 'Snooze'
doveadm mailbox create -s -u $user 'Snooze.Until Friday 18:00'
doveadm mailbox create -s -u $user 'Snooze.Until Monday 7:00'
doveadm mailbox create -s -u $user 'Snooze.Until 7:00'
doveadm mailbox create -s -u $user 'Snooze.Until 18:00'
doveadm mailbox create -s -u $user 'Snooze.For 1 Hour'
"""

import argparse
import datetime
import re
import subprocess
import sys


FOLDERS = ['Snooze.Until Friday 18:00',
           'Snooze.Until Monday 7:00',
           'Snooze.Until 7:00',
           'Snooze.Until 18:00',
           'Snooze.For 1 Hour']


def Debug(msg):
  if args.debug:
    sys.stdout.write(msg + '\n')


def Error(msg):
  sys.stderr.write(msg + '\n')


def UnixTime(mytime):
  epoch = datetime.datetime.fromtimestamp(0)
  return int((mytime - epoch).total_seconds())


class Mail(object):
  """The class that handles snoozing and un-snoozing for a single e-mail."""

  def __init__(self, uid, myfolder):
    self.uid = uid
    self.labels = []
    self.folder = myfolder

  def CheckRelease(self):
    """Check if a mail is ready for release, then move it back to the inbox."""
    for label in self.labels:
      result = re.search('MoveAt(.*)', label, re.IGNORECASE)
      if result:
        timestamp = result.group(1)
        if int(timestamp) < UnixTime(datetime.datetime.now()):
          self.MoveBackToInbox(timestamp)
        else:
          Debug('moving %s at %s' % (self.uid, timestamp))

  def MoveBackToInbox(self, timestamp):
    """Moves mail back to the inbox. Removes labels and sets it unread."""

    Debug('moving %s back to inbox!' % self.uid)
    cmd = [args.doveadm, 'flags', 'remove', '-u', user,
           '\Seen MoveAt%s' % timestamp, 'mailbox', self.folder, 'uid',
           self.uid]
    if 0 != subprocess.call(cmd):
      Error('flags remove before move failed!')
      Error(' '.join(cmd))
    # move back to inbox:
    cmd = [args.doveadm, 'move', '-u', user, 'INBOX', 'mailbox', self.folder,
           'uid', self.uid]
    if 0 != subprocess.call(cmd):
      Error('move back to inbox failed!')
      Error(' '.join(cmd))

  def SetSnooze(self):
    """Sets a label on a mail with a unix timestamp on how long to snooze."""

    newflag = self.FindSnooze()
    if not newflag or newflag in self.labels:
      return None
    if 0 != subprocess.call([args.doveadm,
                             'flags',
                             'add',
                             '-u',
                             user,
                             newflag,
                             'mailbox',
                             self.folder,
                             'uid',
                             self.uid]):
      Error('mail move failed!')

  def FindSnooze(self):
    """Finds out how long to snooze a mail for.

    Returns: unix time when to un-snooze.
    """
    # find out if the Mail has been marked to move already
    for label in self.labels:
      if re.search('MoveAt(.*)', label, re.IGNORECASE):
        return None
    snooze_until = None
    now = datetime.datetime.now()
    Debug('now is %d' % UnixTime(now))
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_of_week = today.weekday()
    if self.folder == 'Snooze.For 1 Hour':
      snooze_until = now + datetime.timedelta(hours=1)
    elif self.folder == 'Snooze.Until 18:00':
      snooze_until = today + datetime.timedelta(hours=18)
      if snooze_until < now:
        snooze_until += datetime.timedelta(days=1)
    elif self.folder == 'Snooze.Until 7:00':
      snooze_until = today + datetime.timedelta(hours=7)
      if snooze_until < now:
        snooze_until += datetime.timedelta(days=1)
    elif self.folder == 'Snooze.Until Monday 7:00':
      snooze_days = 7 - day_of_week
      if snooze_days == 0:
        snooze_days = 7
      snooze_until = today + datetime.timedelta(days=snooze_days, hours=7)
    elif self.folder == 'Snooze.Until Friday 18:00':
      snooze_days = 4 - day_of_week
      if snooze_days < 1:
        snooze_days += 7
      snooze_until = today + datetime.timedelta(days=snooze_days, hours=18)
    else:
      return None
    unix_time = UnixTime(snooze_until)
    Debug('snoozing %s until %s, this is at %d' % (self.uid, snooze_until,
                                                   unix_time))
    return 'MoveAt%d' % unix_time

parser = argparse.ArgumentParser(description=(
    'Marks snoozed mails with a timestamp and moves it back to the inbox. Only '
    'works with the dovecot mailserver. The last argument of this command will '
    'have to be one or more users (e. g. dovecot-snooze.py '
    '--doveadm=/usr/bin/doveadm john mary joe)'))
parser.add_argument('--doveadm', type=str, nargs='?',
                    default='/usr/bin/doveadm', help=(
                        'path to doveadm binary, defaults to /usr/bin/doveadm'))
parser.add_argument('--debug', type=bool, nargs='?', default=False,
                    help=('debug output, set to 1 or true to see more details '
                          'about what is going on.'))
parser.add_argument('users', nargs=argparse.REMAINDER)

args = parser.parse_args()

if not args.users:
  Error('The last argument of this program must be one or more users '
        '(separated by spaces)')
  exit(1)

for user in args.users:
  for folder in FOLDERS:
    try:
      mails = []
      current_mail = None
      cmd = [args.doveadm, 'fetch', '-u', user, 'uid flags', 'mailbox', folder,
             'UNDELETED']
      Debug(' '.join(cmd))
      meta = subprocess.check_output(cmd)
      lines = meta.split('\n')
      for line in lines:
        result = re.search('uid: (.*)', line, re.IGNORECASE)
        if result:
          if current_mail:
            mails.append(current_mail)
          current_mail = Mail(result.group(1), folder)
        result = re.search('flags: (.*)', line, re.IGNORECASE)
        if result:
          current_mail.labels = result.group(1).split(' ')
      if current_mail:
        mails.append(current_mail)
      for mail in mails:
        mail.SetSnooze()
        mail.CheckRelease()
    except:
      Error('unexpected Error!')
