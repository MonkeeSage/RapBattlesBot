#!/usr/bin/env python

# Bot to watch /r/rapbattles for [Battle] submissions and post a poll

import os
import sys
import time
import sqlite3

import praw
import requests

from ConfigParser import SafeConfigParser, NoOptionError


NAME = 'RapBattlesBot'
VERSION = 'v0.3'
CONFIG_FILE = 'RapBattlesBot.ini'

REFRESH_INTERVAL = 60 # seconds to sleep between fetching new submissions
SUBMISSION_LIMIT = 50 # number of new posts to proces

# used below for posting the poll to the thread
REPLY_TEMPLATE = '''Who won?!!

[Submit your vote here](http://www.strawpoll.me/{})

I'm a robot! Beep boop!'''

# sql query aliases. this is bad m'kay, but it's fine for a single-script bot
CREATE_TABLE = '''CREATE TABLE IF NOT EXISTS submission_polls
                  (submission_id text unique,
                   submission_title text,
                   poll_id text)'''
INSERT_INTO = '''INSERT INTO submission_polls VALUES (?, ?, ?)'''
SELECT_FROM = '''SELECT * from submission_polls
                 where submission_id=?'''

CONFIG_ERROR = '''Edit {} to ensure you have defined the the following options:
  client_id
  client_secret
  username
  password'''.format(CONFIG_FILE)


class RapBattlesBot(object):

    def __init__(self, conn):
        # init config
        self.config = SafeConfigParser()
        if os.path.exists(CONFIG_FILE):
            self.config.read(CONFIG_FILE)
        else:
            self.config.add_section('bot')
            self.config.set('bot', 'refresh_interval', str(REFRESH_INTERVAL))
            self.config.set('bot', 'submission_limit', str(SUBMISSION_LIMIT))
            with open(CONFIG_FILE, 'wb') as fh:
                self.config.write(fh)

        # init db
        self.conn = conn
        c = self.conn.cursor()
        c.execute(CREATE_TABLE)
        self.conn.commit()

        # init reddit stuff
        user_agent = '{} {} /r/rapbattles'.format(NAME, VERSION)
        try:
            client_id      = self.config.get('bot', 'client_id')
            client_secret  = self.config.get('bot', 'client_secret')
            username       = self.config.get('bot', 'username')
            password       = self.config.get('bot', 'password')
        except NoOptionError:
            sys.exit(CONFIG_ERROR)

        self.reddit = praw.Reddit(client_id=client_id,
                                  client_secret=client_secret,
                                  username=username,
                                  password=password,
                                  user_agent=user_agent)
        self.sub = self.reddit.subreddit('rapbattles')

        # poll for new submissions
        while True:
            print('----> Fetching new submissions')
            limit = self.config.getint('bot', 'submission_limit')
            for submission in self.sub.new(limit=limit):
                self.process_submission(submission)
            time.sleep(self.config.getint('bot', 'refresh_interval'))

    def process_submission(self, submission):
        if submission.link_flair_text and \
           'BATTLE' in submission.link_flair_text:

            # parse out battler names
            rapperA, rapperB = self.process_title(submission.title)
            if not rapperA or not rapperB:
                print('Could not parse battlers from "{}"'.format(submission.title))

            # don't post the same poll twice
            c = self.conn.cursor()
            r = c.execute(SELECT_FROM, (submission.id,))
            if r.fetchone():
                print('Poll already created for "{}"'.format(submission.title))
                return

            # do the do
            print('Creating poll for "{}"'.format(submission.title))
            poll_id = self.create_poll(submission.title, rapperA, rapperB)

            print('Posting poll (ID: {}) to submission'.format(poll_id))
            submission.reply(REPLY_TEMPLATE.format(poll_id))

            # save poll to db
            c = self.conn.cursor()
            c.execute(INSERT_INTO, (submission.id, submission.title, poll_id))
            self.conn.commit()

            time.sleep(5) # avoid rate limit

    def process_title(self, title):
        """
        Your code is real, your code is raw, your code is authentic.
        And you can't spell "parse" without putting Ars in it.
        -mmmmmmmmmmmmmmmmmmph
        """
        for separator in [' vs ', ' vs. ', ' v ', ' v. ']:
            vs_index = title.lower().find(separator)
            if vs_index > -1:
                break
        if vs_index == -1:
            return None, None

        for separator in ['- ', ': ', ', ', '| ', '] ']:
            left = title.find(separator, 0, vs_index)
            if left > -1:
                break
        rapperA = title[left+1:vs_index].strip(' ')
        if '] ' in rapperA:
            rapperA = rapperA.split('] ')[1]
        if '- ' in rapperA:
            rapperA = rapperA.split('- ')[1]

        for separator in [' -', '- ', ' |', ' :', ' [']:
            right = title.find(separator, vs_index+4)
            if right > -1:
                break
        if right == -1:
            right = len(title)
        rapperB = title[vs_index+4:right].strip(' ')

        print('Parsed out "{}" vs "{}"'.format(rapperA, rapperB))
        return rapperA, rapperB

    def create_poll(self, title, rapperA, rapperB):
        data = {'title': title, 'options': [rapperA, rapperB]}
        response = requests.post('https://strawpoll.me/api/v2/polls', json=data)
        return response.json()['id']


if __name__ == '__main__':
    conn = sqlite3.connect('RapBattlesBot.db')
    try:
        RapBattlesBot(conn)
    except Exception as e:
        print(e)
    conn.close()
